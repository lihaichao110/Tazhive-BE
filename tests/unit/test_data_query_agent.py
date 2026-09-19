"""确定性 text2sql 子图测试：强制校验、错误反馈重试、降级、结果注入与表格下发。"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from app.api.v1 import chat as chat_api
from app.core.langgraph.agents.data_query import (
    SQLDraft,
    _build_generation_prompt,
    build_data_query_agent,
)
from app.core.langgraph.agents.factory import build_intent_agent
from app.core.langgraph.graph.supervisor import build_supervisor_graph
from app.core.langgraph.intent.classifier import IntentResult
from app.core.langgraph.intent.registry import get_intent_spec
from app.services.dataquery.executor import QueryOutcome


class FakeGenerator:
    """按脚本依次返回 SQLDraft；记录每次收到的失败反馈。"""

    def __init__(self, drafts: list[SQLDraft] | None = None, error: Exception | None = None):
        self.drafts = list(drafts or [])
        self.error = error
        self.calls = 0
        self.feedbacks: list[str | None] = []

    async def agenerate(self, messages: list, *, feedback: str | None = None) -> SQLDraft:
        self.feedbacks.append(feedback)
        self.calls += 1
        if self.error:
            raise self.error
        index = min(self.calls - 1, len(self.drafts) - 1)
        return self.drafts[index]


class FakeExecutor:
    """按脚本返回查询结果；记录 guard 归一化后真正执行的 SQL。"""

    def __init__(self, outcomes: list[QueryOutcome] | None = None):
        self.outcomes = list(outcomes or [])
        self.executed: list[str] = []

    def run(self, sql: str) -> QueryOutcome:
        self.executed.append(sql)
        index = min(len(self.executed) - 1, len(self.outcomes) - 1)
        return self.outcomes[index]


class CaptureModel(BaseChatModel):
    """记录回答模型实际收到的消息，并返回固定回答。"""

    content: str
    captured: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "data-query-capture-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.content))])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(list(messages))
        yield ChatGenerationChunk(message=AIMessageChunk(content=self.content))


class CaptureRegistry:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def get_model(self, model_name=None, thinking=None, temperature=None):
        self.calls.append((model_name, thinking))
        return self.model

    def rotate(self):
        pass


class FakeClassifier:
    def __init__(self, intent="data_query", confidence=0.95):
        self.intent = intent
        self.confidence = confidence

    async def classify(self, text: str) -> IntentResult:
        return IntentResult(intent=self.intent, confidence=self.confidence)


@pytest.fixture(autouse=True)
def _mock_rag_retrieval():
    """屏蔽 general 意图子 Agent 的真实 RAG 检索（构建 supervisor 时会一并建出来）。"""
    embedder = AsyncMock()
    embedder.aembed_query.return_value = [0.1, 0.2]
    with (
        patch("app.core.langgraph.middleware.rag.get_embedder", return_value=embedder),
        patch("app.core.langgraph.middleware.rag.retrieve_similar_chunks", return_value=[]),
    ):
        yield


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True


def build_graph(generator, executor, answer):
    return build_data_query_agent(
        get_intent_spec("data_query"),
        generator=generator,
        executor=executor,
        answer_model=answer,
        registry=CaptureRegistry(answer),
    )


@pytest.mark.asyncio
async def test_success_path_executes_normalized_sql_builds_table_and_injects_result():
    generator = FakeGenerator(
        drafts=[
            SQLDraft(sql="SELECT group_name, order_num FROM plan_shows ORDER BY order_num DESC")
        ]
    )
    executor = FakeExecutor(
        outcomes=[
            QueryOutcome(
                columns=["group_name", "order_num"],
                rows=[["方案A", 3], ["方案B", 2]],
            )
        ]
    )
    answer = CaptureModel(
        content=json.dumps({"content": "共 2 个方案", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="投保量排前几的方案"),
                AIMessage(content="上一轮的旧回答，不应进入本轮上下文"),
                HumanMessage(content="方案排序前两名是什么？"),
            ]
        }
    )

    # guard 归一化后自动注入了 LIMIT，再交给执行器
    assert len(executor.executed) == 1
    assert "FROM plan_shows" in executor.executed[0]
    assert "LIMIT" in executor.executed[0].upper()

    # 查询结果渲染成 Markdown 表格，列名兜底翻译为中文表头
    table = result.get("table_markdown")
    assert isinstance(table, str)
    lines = table.splitlines()
    assert lines[0] == "| 方案名称 | 分类内展示顺序 |"
    assert lines[1] == "| --- | --- |"
    assert "| 方案A | 3 |" in lines
    assert "| 方案B | 2 |" in lines
    assert result.get("x_card") is None

    # 回答模型的系统提示注入了查询结果（列名同样已翻译）与表格说明，且旧 Assistant 历史被隔离
    system_prompt = answer.captured[0][0].content
    assert "<query_result>" in system_prompt
    assert "方案A" in system_prompt
    assert "方案名称" in system_prompt
    assert "服务端自动附在回答末尾" in system_prompt
    assert "上一轮的旧回答" not in system_prompt
    assert not any(
        getattr(message, "content", None) == "上一轮的旧回答，不应进入本轮上下文"
        for message in answer.captured[0]
    )

    # 最终回复
    assert result["messages"][-1].content == answer.content
    assert result.get("sql_error") is None


def test_generation_prompt_requires_chinese_output_aliases():
    """SQL 生成规则要求每个输出列带中文 AS 别名，表头对用户才可读。"""
    prompt = _build_generation_prompt(["在售产品按分类统计数量"], feedback=None)
    assert "中文 AS 别名" in prompt
    assert 'AS "产品分类"' in prompt


@pytest.mark.asyncio
async def test_unknown_columns_pass_through_without_label_mapping():
    """COLUMN_LABELS 只兜底已知列名，模型自造的未知别名原样展示。"""
    generator = FakeGenerator(
        drafts=[SQLDraft(sql="SELECT status, weird_metric FROM insurance_applications")]
    )
    executor = FakeExecutor(
        outcomes=[
            QueryOutcome(
                columns=["status", "weird_metric"],
                rows=[["CONFIRMED", 3], ["IN_PROGRESS", 1]],
            )
        ]
    )
    answer = CaptureModel(
        content=json.dumps({"content": "统计完成", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke({"messages": [HumanMessage(content="各状态投保单数")]})

    assert result.get("query_columns") == ["投保状态", "weird_metric"]
    lines = result.get("table_markdown").splitlines()
    assert lines[0] == "| 投保状态 | weird_metric |"
    assert "| CONFIRMED | 3 |" in lines


@pytest.mark.asyncio
async def test_guard_failure_feeds_back_and_second_attempt_succeeds():
    generator = FakeGenerator(
        drafts=[
            SQLDraft(sql="SELECT * FROM users"),
            SQLDraft(sql="SELECT COUNT(*) AS total FROM products"),
        ]
    )
    executor = FakeExecutor(outcomes=[QueryOutcome(columns=["total"], rows=[[12]])])
    answer = CaptureModel(
        content=json.dumps({"content": "共 12 款", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke({"messages": [HumanMessage(content="产品有几款")]})

    assert generator.calls == 2
    feedback = generator.feedbacks[1]
    assert feedback is not None and "不允许查询表" in feedback
    assert "SELECT * FROM users" in feedback
    # 白名单拦截的 SQL 不会到达执行器
    assert len(executor.executed) == 1
    assert "FROM products" in executor.executed[0]
    assert result.get("sql_error") is None
    # 单标量结果不出表格
    assert result.get("table_markdown") is None
    assert '"rows": [[12]]' in answer.captured[0][0].content


@pytest.mark.asyncio
async def test_repeated_failure_degrades_to_honest_answer_without_card():
    generator = FakeGenerator(drafts=[SQLDraft(sql="SELECT * FROM users")])
    executor = FakeExecutor()
    answer = CaptureModel(
        content=json.dumps({"content": "查询失败", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke({"messages": [HumanMessage(content="用户数据")]})

    assert generator.calls == 2  # 首次 + 带反馈的 1 次重试，之后不再生成
    assert executor.executed == []
    assert result.get("table_markdown") is None
    assert "校验未通过" in answer.captured[0][0].content


@pytest.mark.asyncio
async def test_unanswerable_question_skips_execution():
    generator = FakeGenerator(
        drafts=[SQLDraft(sql=None, unanswerable_reason="系统没有存储用户聊天内容")]
    )
    executor = FakeExecutor()
    answer = CaptureModel(
        content=json.dumps({"content": "查不了", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke({"messages": [HumanMessage(content="大家都在聊什么")]})

    assert generator.calls == 1
    assert executor.executed == []
    assert result.get("table_markdown") is None
    assert "没有存储用户聊天内容" in answer.captured[0][0].content


@pytest.mark.asyncio
async def test_generator_exception_degrades_gracefully():
    generator = FakeGenerator(error=TimeoutError("planner timeout"))
    executor = FakeExecutor()
    answer = CaptureModel(
        content=json.dumps({"content": "稍后再试", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    result = await graph.ainvoke({"messages": [HumanMessage(content="本月投保量")]})

    assert executor.executed == []
    assert result.get("table_markdown") is None
    assert "暂时不可用" in answer.captured[0][0].content


@pytest.mark.asyncio
async def test_truncated_result_flag_reaches_answer_prompt():
    generator = FakeGenerator(drafts=[SQLDraft(sql="SELECT id FROM insurance_events")])
    executor = FakeExecutor(
        outcomes=[
            QueryOutcome(
                columns=["id"],
                rows=[["a"], ["b"]],
                truncated=True,
            )
        ]
    )
    answer = CaptureModel(
        content=json.dumps({"content": "部分结果", "charts": []}, ensure_ascii=False)
    )
    graph = build_graph(generator, executor, answer)

    await graph.ainvoke({"messages": [HumanMessage(content="所有事件")]})

    system_prompt = answer.captured[0][0].content
    assert "仅为前 2 行" in system_prompt


@pytest.mark.asyncio
async def test_answer_tokens_are_not_forwarded_to_custom_stream():
    """data_query 回答不做 token 透传：表格要并入信封后由 chat.py 整帧下发，
    透传会让前端累积的中间内容与最终合并结果不一致（SSE 只能追加）。"""
    generator = FakeGenerator(drafts=[SQLDraft(sql="SELECT name FROM products")])
    executor = FakeExecutor(outcomes=[QueryOutcome(columns=["name"], rows=[["甲"], ["乙"]])])
    answer = CaptureModel(content=json.dumps({"content": "两款", "charts": []}, ensure_ascii=False))
    graph = build_graph(generator, executor, answer)

    custom_payloads = []
    async for mode, payload in graph.astream(
        {"messages": [HumanMessage(content="查产品")]},
        config={"configurable": {"thread_id": "t-dq-no-stream"}},
        stream_mode=["custom", "messages"],
    ):
        if mode == "custom":
            custom_payloads.append(payload)

    assert custom_payloads == []


def _build_supervisor(generator, executor, answer):
    registry = CaptureRegistry(answer)
    classifier = FakeClassifier("data_query")

    def agent_builder(spec):
        if spec.id == "data_query":
            return build_data_query_agent(
                spec,
                generator=generator,
                executor=executor,
                answer_model=answer,
                registry=registry,
            )
        return build_intent_agent(spec, model=answer, registry=registry)

    graph = build_supervisor_graph(
        classifier=classifier,
        agent_builder=agent_builder,
        checkpointer=InMemorySaver(),
    )
    return graph, classifier


def _delta_content(payload: dict) -> str:
    if "choices" not in payload:
        return ""
    return payload["choices"][0]["delta"].get("content") or ""


async def _collect_frames(graph, thread_id: str, user_text: str) -> list[str]:
    frames = []
    async for frame in chat_api.stream_chat_response(
        thread_id=thread_id,
        model="fake-model",
        agent=graph,
        input_state={
            "messages": [HumanMessage(content=user_text)],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": thread_id}},
        last_user_content=user_text,
    ):
        frames.append(frame)
    return frames


@pytest.mark.asyncio
async def test_sse_merges_table_into_envelope_and_persists(monkeypatch):
    """端到端契约：表格并入信封 content 整帧下发（仍是合法 JSON），流式与落库同形。"""
    generator = FakeGenerator(drafts=[SQLDraft(sql="SELECT name FROM products")])
    executor = FakeExecutor(outcomes=[QueryOutcome(columns=["name"], rows=[["甲"], ["乙"]])])
    answer = CaptureModel(
        content=json.dumps({"content": "共 2 款", "charts": []}, ensure_ascii=False)
    )
    graph, _ = _build_supervisor(generator, executor, answer)
    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)

    frames = await _collect_frames(graph, "t-dq-sse", "有哪些产品")

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    # 回答不做 token 透传：非空正文增量只有合并后的整帧
    contents = [content for content in map(_delta_content, payloads) if content]
    assert len(contents) == 1
    streamed = contents[0]
    envelope = json.loads(streamed)
    assert envelope["content"].startswith("共 2 款")
    assert "| 产品名称 |" in envelope["content"]
    assert "| 甲 |" in envelope["content"]
    assert envelope["charts"] == []

    # 合并帧在 stop 帧之前、[DONE] 收尾
    content_indexes = [i for i, p in enumerate(payloads) if _delta_content(p)]
    stop_indexes = [
        i
        for i, p in enumerate(payloads)
        if p.get("choices", [{}])[0].get("finish_reason") == "stop"
    ]
    assert len(stop_indexes) == 1
    assert content_indexes[0] < stop_indexes[0]
    assert frames[-1] == "data: [DONE]\n\n"

    # 落库的 assistant 正文与流式输出同形，历史重放才能复现表格
    assert session.committed is True
    assert [message.role for message in session.added] == ["user", "assistant"]
    assert session.added[-1].content == streamed


@pytest.mark.asyncio
async def test_sse_sends_answer_when_query_has_no_table(monkeypatch):
    """回归：count 类单标量结果不出表格，data_query 回答仍须整帧补发，
    不能只给客户端一个空 stop 帧（该意图 token 透传是关闭的）。"""
    generator = FakeGenerator(
        drafts=[SQLDraft(sql="SELECT COUNT(*) AS total FROM insurance_events")]
    )
    executor = FakeExecutor(outcomes=[QueryOutcome(columns=["total"], rows=[[12]])])
    answer = CaptureModel(
        content=json.dumps({"content": "共 12 笔", "charts": []}, ensure_ascii=False)
    )
    graph, _ = _build_supervisor(generator, executor, answer)
    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)

    frames = await _collect_frames(graph, "t-dq-sse-no-table", "本月有多少笔投保单")

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    # 无表格：正文原样整帧补发，不需要合并信封
    contents = [content for content in map(_delta_content, payloads) if content]
    assert contents == [answer.content]

    stop_indexes = [
        i
        for i, p in enumerate(payloads)
        if p.get("choices", [{}])[0].get("finish_reason") == "stop"
    ]
    assert len(stop_indexes) == 1
    assert payloads.index(next(p for p in payloads if _delta_content(p))) < stop_indexes[0]
    assert frames[-1] == "data: [DONE]\n\n"

    # 落库与流式同形
    assert session.committed is True
    assert [message.role for message in session.added] == ["user", "assistant"]
    assert session.added[-1].content == answer.content


@pytest.mark.asyncio
async def test_table_markdown_does_not_leak_into_later_turns(monkeypatch):
    """回归：data_query 轮的表格不能在 checkpoint 里残留到后续轮次。"""
    generator = FakeGenerator(drafts=[SQLDraft(sql="SELECT name FROM products")])
    executor = FakeExecutor(outcomes=[QueryOutcome(columns=["name"], rows=[["甲"], ["乙"]])])
    answer = CaptureModel(
        content=json.dumps({"content": "共 2 款", "charts": []}, ensure_ascii=False)
    )
    graph, classifier = _build_supervisor(generator, executor, answer)
    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)
    config = {"configurable": {"thread_id": "t-dq-table-leak"}}

    # 第 1 轮：data_query 意图写入表格
    await graph.ainvoke(
        {"messages": [HumanMessage(content="有哪些产品")], "system_prompt": "你是测试助手"},
        config=config,
    )
    values = (await graph.aget_state(config)).values
    assert isinstance(values.get("table_markdown"), str)

    # 第 2 轮：同 thread 切换为 chitchat，流式输出与落库都不应再带表格
    classifier.intent = "chitchat"
    answer.content = "你好呀"
    frames = await _collect_frames(graph, "t-dq-table-leak", "你好")

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    assert not any("| --- |" in _delta_content(item) for item in payloads)
    assert (await graph.aget_state(config)).values.get("table_markdown") is None
    assert "| --- |" not in session.added[-1].content
