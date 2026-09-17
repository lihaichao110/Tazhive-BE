"""确定性 text2sql 子图测试：强制校验、错误反馈重试、降级与结果注入。"""

import json

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from app.core.langgraph.agents.data_query import (
    DATA_SURFACE_PREFIX,
    SQLDraft,
    build_data_query_agent,
)
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

    def get_model(self, model_name=None, thinking=None):
        self.calls.append((model_name, thinking))
        return self.model

    def rotate(self):
        pass


def build_graph(generator, executor, answer):
    return build_data_query_agent(
        get_intent_spec("data_query"),
        generator=generator,
        executor=executor,
        answer_model=answer,
        registry=CaptureRegistry(answer),
    )


@pytest.mark.asyncio
async def test_success_path_executes_normalized_sql_builds_card_and_injects_result():
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

    # 表格卡片信封
    envelope = result.get("x_card")
    assert isinstance(envelope, dict)
    assert envelope["surfaceId"].startswith(f"{DATA_SURFACE_PREFIX}_")
    create_surface = envelope["commands"][0]["createSurface"]
    assert create_surface["surfaceId"] == envelope["surfaceId"]
    table_component = envelope["commands"][1]["updateComponents"]["components"][0]
    assert table_component["component"] == "DataTable"
    assert table_component["columns"] == ["group_name", "order_num"]
    # 卡片单元格统一转字符串渲染
    assert table_component["rows"] == [["方案A", "3"], ["方案B", "2"]]

    # 回答模型的系统提示注入了查询结果，且旧 Assistant 历史被隔离
    system_prompt = answer.captured[0][0].content
    assert "<query_result>" in system_prompt
    assert "方案A" in system_prompt
    assert "上一轮的旧回答" not in system_prompt
    assert not any(
        getattr(message, "content", None) == "上一轮的旧回答，不应进入本轮上下文"
        for message in answer.captured[0]
    )

    # 最终回复
    assert result["messages"][-1].content == answer.content
    assert result.get("sql_error") is None


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
    # 单标量结果不出卡片
    assert result.get("x_card") is None
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
    assert result.get("x_card") is None
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
    assert result.get("x_card") is None
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
    assert result.get("x_card") is None
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
