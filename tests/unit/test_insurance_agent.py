"""insurance 确定性子图测试：查库出卡片、降级、以及 SSE 围栏的下发与落库。

用脚本式假模型 + 假 plan_loader 避免真实 LLM 与数据库调用。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from app.api.v1 import chat as chat_api
from app.core.langgraph.agents.factory import build_intent_agent
from app.core.langgraph.agents.insurance import (
    PLAN_SURFACE_PREFIX,
    PlanFilter,
    build_insurance_agent,
)
from app.core.langgraph.graph.supervisor import build_supervisor_graph
from app.core.langgraph.intent.classifier import IntentResult
from app.core.langgraph.intent.registry import get_intent_spec
from app.models.plan_show import PlanShow
from app.services.plans import PlanQueryResult

ANSWER_TEXT = "已为您找到 2 款在售方案，可以先看看保障范围。"

TITLES = ["寿险", "健康", "年金", "万能"]


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


class ScriptedCaptureModel(BaseChatModel):
    """返回固定回复的假模型；记录每次调用收到的系统提示。"""

    responses: list = []
    index: int = 0
    captured: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted-capture-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _peek(self) -> BaseMessage:
        return self.responses[min(self.index, len(self.responses) - 1)]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.captured.append(list(messages))
        message = self._peek()
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(list(messages))
        text = self._peek().content
        self.index += 1
        for i in range(0, len(text), 2):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[i : i + 2]))

    @property
    def system_prompt(self) -> str:
        messages = self.captured[-1]
        return next(m.content for m in messages if m.type == "system")


class PassthroughRegistry:
    """始终返回预置模型的假注册表。"""

    def __init__(self, model):
        self.model = model

    def get_model(self, model_name=None, thinking=None):
        return self.model

    def rotate(self):
        pass


class FakeClassifier:
    def __init__(self, intent="insurance", confidence=0.95):
        self.intent = intent
        self.confidence = confidence

    async def classify(self, text: str) -> IntentResult:
        return IntentResult(intent=self.intent, confidence=self.confidence)


class FakePlanPlanner:
    """按脚本返回筛选条件；记录收到的消息与分类列表。"""

    def __init__(self, plan_filter: PlanFilter | None = None, error: Exception | None = None):
        self.plan_filter = plan_filter or PlanFilter()
        self.error = error
        self.calls: list[tuple[list, list[str]]] = []

    async def aplan(self, messages: list, *, available_titles: list[str]) -> PlanFilter:
        self.calls.append((list(messages), list(available_titles)))
        if self.error:
            raise self.error
        return self.plan_filter


def _row(group_code="G0264", **overrides) -> PlanShow:
    values = {
        "group_code": group_code,
        "group_name": f"方案{group_code}",
        "contents": "卖点一\r\n卖点二",
        "order_num": 1047,
        "title_id": 1,
        "title": "寿险",
        "title_ord_num": 1,
        "img": "https://example.com/a.png",
        "has_sale": "2",
        "insur_list": ["AYR"],
        "is_more_insur": 0,
        "is_approve": 1,
        "is_irisk": 2,
    }
    values.update(overrides)
    return PlanShow(**values)


def _build_insurance(plan_loader, planner: FakePlanPlanner | None = None):
    model = ScriptedCaptureModel(responses=[AIMessage(content=ANSWER_TEXT)])
    agent = build_insurance_agent(
        get_intent_spec("insurance"),
        filter_planner=planner or FakePlanPlanner(),
        plan_loader=plan_loader,
        titles_loader=lambda: TITLES,
        answer_model=model,
        registry=PassthroughRegistry(model),
    )
    return agent, model


async def _invoke(agent, thread_id):
    return await agent.ainvoke(
        {
            "messages": [HumanMessage(content="我想买份保险")],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": thread_id}},
    )


def _fence_body(fence: str) -> dict:
    body = fence.removeprefix("\n\n```a2ui\n").removesuffix("\n```")
    return json.loads(body)


@pytest.mark.asyncio
async def test_query_node_writes_envelope_and_prompt_reports_count():
    planner = FakePlanPlanner()
    agent, model = _build_insurance(
        lambda _filter=None: PlanQueryResult(
            rows=[_row(), _row(group_code="G0208")], available_titles=TITLES
        ),
        planner=planner,
    )

    result = await _invoke(agent, "t-insurance-ok")

    # 筛选节点确实运行过，且把分类列表交给了提取器
    assert len(planner.calls) == 1
    assert planner.calls[0][1] == TITLES

    envelope = result["x_card"]
    assert envelope is not None
    assert envelope["surfaceId"].startswith(f"{PLAN_SURFACE_PREFIX}_")
    assert len(envelope["commands"]) == 3
    components = envelope["commands"][1]["updateComponents"]["components"]
    assert components[0]["id"] == "root"
    assert components[0]["children"] == ["plan_G0264", "plan_G0208"]

    # 模型只被要求写说明，且知道卡片已由服务端下发
    assert result["messages"][-1].content == ANSWER_TEXT
    assert "下发了 2 张卡片" in model.system_prompt
    assert "不要重复罗列产品名称" in model.system_prompt


@pytest.mark.asyncio
async def test_each_turn_gets_unique_surface_id():
    agent, _ = _build_insurance(
        lambda _filter=None: PlanQueryResult(rows=[_row()], available_titles=TITLES)
    )

    first = await _invoke(agent, "t-insurance-surface-1")
    second = await _invoke(agent, "t-insurance-surface-2")

    assert first["x_card"]["surfaceId"] != second["x_card"]["surfaceId"]


@pytest.mark.asyncio
async def test_query_failure_degrades_to_text_without_touching_answer():
    def broken_loader(_filter=None):
        raise RuntimeError("db down")

    agent, model = _build_insurance(broken_loader)

    result = await _invoke(agent, "t-insurance-fail")

    assert result["x_card"] is None
    assert result["messages"][-1].content == ANSWER_TEXT
    assert "未取到在售方案数据" in model.system_prompt
    assert "不要凭记忆编造产品名称与保费" in model.system_prompt


@pytest.mark.asyncio
async def test_no_rows_degrades_to_text():
    agent, model = _build_insurance(
        lambda _filter=None: PlanQueryResult(rows=[], available_titles=TITLES)
    )

    result = await _invoke(agent, "t-insurance-empty")

    assert result["x_card"] is None
    assert result["messages"][-1].content == ANSWER_TEXT
    assert "未取到在售方案数据" in model.system_prompt


def _build_supervisor(plan_loader, planner: FakePlanPlanner | None = None):
    answer_model = ScriptedCaptureModel(responses=[AIMessage(content=ANSWER_TEXT)])
    registry = PassthroughRegistry(answer_model)
    classifier = FakeClassifier("insurance")

    def agent_builder(spec):
        if spec.id == "insurance":
            return build_insurance_agent(
                spec,
                filter_planner=planner or FakePlanPlanner(),
                plan_loader=plan_loader,
                titles_loader=lambda: TITLES,
                answer_model=answer_model,
                registry=registry,
            )
        return build_intent_agent(spec, model=answer_model, registry=registry)

    graph = build_supervisor_graph(
        classifier=classifier,
        agent_builder=agent_builder,
        checkpointer=InMemorySaver(),
    )
    return graph, classifier


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


def _delta_content(payload: dict) -> str:
    if "choices" not in payload:
        return ""
    return payload["choices"][0]["delta"].get("content") or ""


@pytest.mark.asyncio
async def test_sse_emits_fence_before_stop_and_persists_it(monkeypatch):
    """端到端契约：卡片围栏在 stop 帧之前下发，并与正文一起落库供历史重放。"""
    graph, _ = _build_supervisor(
        lambda _filter=None: PlanQueryResult(
            rows=[_row(), _row(group_code="G0208")], available_titles=TITLES
        )
    )
    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)

    frames = []
    async for frame in chat_api.stream_chat_response(
        thread_id="t-insurance-sse",
        model="fake-model",
        agent=graph,
        input_state={
            "messages": [HumanMessage(content="我想买份保险")],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": "t-insurance-sse"}},
        last_user_content="我想买份保险",
    ):
        frames.append(frame)

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    fence_indexes = [
        index
        for index, item in enumerate(payloads)
        if _delta_content(item).startswith("\n\n```a2ui")
    ]
    stop_indexes = [
        index
        for index, item in enumerate(payloads)
        if item.get("choices", [{}])[0].get("finish_reason") == "stop"
    ]

    assert len(fence_indexes) == 1
    assert len(stop_indexes) == 1
    assert fence_indexes[0] < stop_indexes[0]
    assert frames[-1] == "data: [DONE]\n\n"

    # 正文流 = 模型说明 + 卡片围栏，且围栏能被前端解析成完整信封
    streamed = "".join(_delta_content(item) for item in payloads)
    fence = _delta_content(payloads[fence_indexes[0]])
    assert streamed == f"{ANSWER_TEXT}{fence}"
    envelope = _fence_body(fence)
    assert envelope["surfaceId"].startswith(f"{PLAN_SURFACE_PREFIX}_")
    assert [next(key for key in c if key != "version") for c in envelope["commands"]] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]

    # 落库的 assistant 正文与流式输出同形（同一段围栏），历史重放才能复现卡片
    assert session.committed is True
    assert [message.role for message in session.added] == ["user", "assistant"]
    assert session.added[-1].content == streamed


@pytest.mark.asyncio
async def test_card_envelope_does_not_leak_into_later_turns(monkeypatch):
    """回归：insurance 轮的信封不能在 checkpoint 里残留到后续轮次。

    修复前 intent_node 不清 x_card，之后任意意图（如 chitchat）每轮的
    SSE 尾帧都会重复下发同一张旧卡片，并随 assistant 消息落库。
    """
    graph, classifier = _build_supervisor(
        lambda _filter=None: PlanQueryResult(rows=[_row()], available_titles=TITLES)
    )
    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)
    config = {"configurable": {"thread_id": "t-card-leak"}}

    # 第 1 轮：insurance 意图查库写入卡片信封
    await graph.ainvoke(
        {"messages": [HumanMessage(content="推荐一份保险")], "system_prompt": "你是测试助手"},
        config=config,
    )
    envelope = (await graph.aget_state(config)).values.get("x_card")
    assert isinstance(envelope, dict) and envelope.get("commands")

    # 第 2 轮：同 thread 切换为 chitchat，流式输出与落库都不应再带卡片围栏
    classifier.intent = "chitchat"
    frames = []
    async for frame in chat_api.stream_chat_response(
        thread_id="t-card-leak",
        model="fake-model",
        agent=graph,
        input_state={
            "messages": [HumanMessage(content="你知道李海超这个人么")],
            "system_prompt": "你是测试助手",
        },
        config=config,
        last_user_content="你知道李海超这个人么",
    ):
        frames.append(frame)

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    assert not any("```a2ui" in _delta_content(item) for item in payloads)
    assert (await graph.aget_state(config)).values.get("x_card") is None
    assert [message.role for message in session.added] == ["user", "assistant"]
    assert "```a2ui" not in session.added[-1].content


# ---------------- 筛选条件提取与按条件出卡 ----------------


@pytest.mark.asyncio
async def test_category_filter_passes_condition_to_loader_and_scopes_cards():
    """「万能险都有什么」：只出该分类卡片，回答提示说明筛选口径。"""
    planner = FakePlanPlanner(PlanFilter(category="万能"))
    loader_filters = []

    def loader(plan_filter=None):
        loader_filters.append(plan_filter)
        return PlanQueryResult(
            rows=[
                _row(title="万能", title_id=4),
                _row(group_code="G0209", title="万能", title_id=4),
            ],
            mode="filtered",
            matched_by="category",
            available_titles=TITLES,
        )

    agent, model = _build_insurance(loader, planner=planner)

    result = await agent.ainvoke(
        {
            "messages": [HumanMessage(content="现在正在售卖的万能险都有什么")],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": "t-insurance-category"}},
    )

    # 提取出的结构化条件原样传给了确定性查询层
    assert loader_filters == [{"category": "万能", "keywords": []}]

    envelope = result["x_card"]
    assert envelope is not None
    children = envelope["commands"][1]["updateComponents"]["components"][0]["children"]
    assert children == ["plan_G0264", "plan_G0209"]

    assert "分类「万能」" in model.system_prompt
    assert "下发了 2 张匹配卡片" in model.system_prompt
    assert "筛选" in model.system_prompt


@pytest.mark.asyncio
async def test_keyword_relaxed_match_reports_keyword_scope():
    """分类没命中但方案名/卖点放宽命中：口径说明按关键词表述。"""
    planner = FakePlanPlanner(PlanFilter(category="重疾"))
    agent, model = _build_insurance(
        lambda _filter=None: PlanQueryResult(
            rows=[_row(group_code="G0301", contents="重疾与医疗保障")],
            mode="filtered",
            matched_by="keyword",
            available_titles=TITLES,
        ),
        planner=planner,
    )

    result = await _invoke(agent, "t-insurance-keyword")

    assert result["x_card"] is not None
    assert "关键词「重疾」" in model.system_prompt


@pytest.mark.asyncio
async def test_no_match_suppresses_card_and_guides_to_categories():
    """零命中：不出卡片，回答提示列出分类引导用户。"""
    planner = FakePlanPlanner(PlanFilter(category="车险"))
    agent, model = _build_insurance(
        lambda _filter=None: PlanQueryResult(rows=[], mode="no_match", available_titles=TITLES),
        planner=planner,
    )

    result = await _invoke(agent, "t-insurance-no-match")

    assert result["x_card"] is None
    assert "没有匹配到任何方案" in model.system_prompt
    assert "寿险、健康、年金、万能" in model.system_prompt
    assert "不要编造产品名称与保费" in model.system_prompt


@pytest.mark.asyncio
async def test_planner_failure_degrades_to_full_catalog():
    """提取失败降级为泛化全量：loader 收到空条件，行为与改造前一致。"""
    planner = FakePlanPlanner(error=TimeoutError("planner timeout"))
    loader_filters = []

    def loader(plan_filter=None):
        loader_filters.append(plan_filter)
        return PlanQueryResult(rows=[_row(), _row(group_code="G0208")], available_titles=TITLES)

    agent, model = _build_insurance(loader, planner=planner)

    result = await _invoke(agent, "t-insurance-planner-fail")

    assert loader_filters == [{"category": None, "keywords": []}]
    assert result["x_card"] is not None
    # 泛化全量走「查询并下发」文案，不出现筛选口径
    assert "已查询在售方案并下发了 2 张卡片" in model.system_prompt


@pytest.mark.asyncio
async def test_multi_turn_extraction_sees_prior_user_answers():
    """上一轮被追问、本轮补充关键词：提取器应看到多条用户消息。"""
    planner = FakePlanPlanner(PlanFilter(category=None, keywords=["父母"]))

    agent, _ = _build_insurance(
        lambda _filter=None: PlanQueryResult(
            rows=[_row(group_code="G0401", contents="适合父母的保障")],
            mode="filtered",
            matched_by="keyword",
            available_titles=TITLES,
        ),
        planner=planner,
    )

    await agent.ainvoke(
        {
            "messages": [
                HumanMessage(content="我想买份保险"),
                AIMessage(content="请问是想给谁投保？"),
                HumanMessage(content="给父母买，老人家的"),
            ],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": "t-insurance-multi-turn"}},
    )

    messages_seen = planner.calls[0][0]
    human_texts = [m.content for m in messages_seen if isinstance(m, HumanMessage)]
    assert "给父母买，老人家的" in human_texts
