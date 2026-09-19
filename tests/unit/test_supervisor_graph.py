"""supervisor 图测试：意图路由、协议拼接、子图流式与记忆。

使用脚本式假模型避免真实 LLM 调用；关键验证点是子 Agent（create_agent
编译图）作为图节点挂载后，token 流（custom）与完整消息（messages）能否
冒泡到顶层 astream——chat.py 的 SSE 与落库依赖这一行为。
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    message_chunk_to_message,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from app.api.v1 import chat as chat_api
from app.api.v1.chat import _accumulate_model_message, _is_model_node
from app.core.langgraph.agents.factory import build_intent_agent
from app.core.langgraph.graph.supervisor import build_supervisor_graph
from app.core.langgraph.intent.classifier import IntentResult
from app.core.langgraph.intent.registry import INTENT_SPECS
from app.core.langgraph.prompts.system_chat import (
    CHART_ANALYSIS_PROTOCOL_PROMPT,
    CHART_RESPONSE_PROTOCOL_PROMPT,
    SEARCH_PROTOCOL_PROMPT,
    SYSTEM_CHAT_PROMPT,
)


@pytest.fixture(autouse=True)
def _mock_rag_retrieval():
    """屏蔽 general 意图子 Agent 的真实 RAG 检索（避免网络/DB 调用与重试退避）。"""
    embedder = AsyncMock()
    embedder.aembed_query.return_value = [0.1, 0.2]
    with (
        patch(
            "app.core.langgraph.middleware.rag.get_embedder",
            return_value=embedder,
        ),
        patch(
            "app.core.langgraph.middleware.rag.retrieve_similar_chunks",
            return_value=[],
        ),
    ):
        yield


class ScriptedCaptureModel(BaseChatModel):
    """按脚本返回预设消息的假模型；记录每次调用收到的完整消息列表。"""

    responses: list = []
    index: int = 0
    captured: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted-capture-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _record(self, messages):
        self.captured.append(list(messages))

    def _peek(self) -> BaseMessage:
        return self.responses[min(self.index, len(self.responses) - 1)]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._record(messages)
        message = self._peek()
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return self._generate(messages, stop, run_manager, **kwargs)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self._record(messages)
        message = self._peek()
        self.index += 1
        text = message.content if isinstance(message.content, str) else ""
        for i in range(0, len(text), 2):
            yield ChatGenerationChunk(message=AIMessageChunk(content=text[i : i + 2]))


class FakeClassifier:
    """返回固定意图的假分类器。"""

    def __init__(self, intent="general", confidence=0.9):
        self.intent = intent
        self.confidence = confidence
        self.last_text = None

    async def classify(self, text: str) -> IntentResult:
        self.last_text = text
        return IntentResult(intent=self.intent, confidence=self.confidence)


class PassthroughRegistry:
    """始终返回预置模型的假注册表。"""

    def __init__(self, model):
        self.model = model

    def get_model(self, model_name=None, thinking=None, temperature=None):
        return self.model

    def rotate(self):
        pass


def _build_supervisor(intent: str, checkpointer=None):
    """构建测试用 supervisor 图：每个意图的子 Agent 都用脚本假模型。"""
    classifier = FakeClassifier(intent=intent)
    models = {}

    def agent_builder(spec):
        model = ScriptedCaptureModel(responses=[AIMessage(content=f"reply-from-{spec.id}")])
        models[spec.id] = model
        return build_intent_agent(spec, model=model, registry=PassthroughRegistry(model))

    graph = build_supervisor_graph(
        classifier=classifier,
        agent_builder=agent_builder,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )
    return graph, models, classifier


def _invoke(graph, content, thread_id, system_prompt="你是测试助手"):
    return graph.ainvoke(
        {
            "messages": [HumanMessage(content=content)],
            "system_prompt": system_prompt,
        },
        config={"configurable": {"thread_id": thread_id}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("intent_id", list(INTENT_SPECS.keys()))
async def test_routes_to_matching_subagent(intent_id):
    graph, models, classifier = _build_supervisor(intent_id)

    result = await _invoke(graph, "用户消息", f"t-{intent_id}")

    assert result["intent"] == intent_id
    assert result["messages"][-1].content == f"reply-from-{intent_id}"
    # 只有被路由到的意图的子 Agent 真正调用了模型
    called = [spec_id for spec_id, m in models.items() if m.captured]
    assert called == [intent_id]
    assert classifier.last_text == "用户消息"


@pytest.mark.asyncio
async def test_unknown_classifier_intent_falls_back_to_general():
    graph, models, _ = _build_supervisor("bogus-intent")

    result = await _invoke(graph, "你好", "t-fallback")

    assert result["intent"] == "general"
    assert result["messages"][-1].content == "reply-from-general"


@pytest.mark.asyncio
async def test_protocol_composed_per_intent():
    graph, models, _ = _build_supervisor("chart_analysis")
    await _invoke(graph, "画个柱状图", "t-chart")

    system_messages = [m for m in models["chart_analysis"].captured[0] if m.type == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].content.startswith("你是测试助手")
    assert CHART_ANALYSIS_PROTOCOL_PROMPT in system_messages[0].content


@pytest.mark.asyncio
async def test_chitchat_keeps_base_prompt_without_protocol():
    graph, models, _ = _build_supervisor("chitchat")
    await _invoke(graph, "你好呀", "t-chitchat")

    system_messages = [m for m in models["chitchat"].captured[0] if m.type == "system"]
    assert len(system_messages) == 1
    assert system_messages[0].content == "你是测试助手"


@pytest.mark.asyncio
async def test_general_gets_chart_envelope_protocol():
    graph, models, _ = _build_supervisor("general")
    await _invoke(graph, "报销流程是什么", "t-general")

    system_messages = [m for m in models["general"].captured[0] if m.type == "system"]
    assert CHART_RESPONSE_PROTOCOL_PROMPT in system_messages[0].content


@pytest.mark.asyncio
async def test_search_gets_json_and_source_protocol_without_rag():
    graph, models, _ = _build_supervisor("search")
    await _invoke(graph, "搜索今天的新闻", "t-search")

    system_messages = [m for m in models["search"].captured[0] if m.type == "system"]
    prompt = system_messages[0].content
    assert CHART_RESPONSE_PROTOCOL_PROMPT in prompt
    assert SEARCH_PROTOCOL_PROMPT in prompt
    assert "Markdown 链接" in prompt
    assert "已由服务端强制执行联网搜索" in prompt
    assert "不要声称自己没有联网搜索能力" in prompt


@pytest.mark.asyncio
async def test_default_base_prompt_when_state_missing():
    graph, models, _ = _build_supervisor("chitchat")
    await graph.ainvoke(
        {"messages": [HumanMessage(content="嗨")]},
        config={"configurable": {"thread_id": "t-default-prompt"}},
    )
    # 不传 system_prompt 时使用默认身份提示词
    system_messages = [m for m in models["chitchat"].captured[0] if m.type == "system"]
    assert system_messages[0].content == SYSTEM_CHAT_PROMPT


@pytest.mark.asyncio
async def test_tokens_stream_to_top_level():
    """SSE 数据源契约：token 增量从子图冒泡到顶层 custom 流，
    完整消息出现在 messages 流且能被 chat.py 的模型节点过滤命中。"""
    graph, models, _ = _build_supervisor("insurance")

    token_text = ""
    final_message = None
    ai_node_names = set()
    namespaces = set()
    async for namespace, mode, payload in graph.astream(
        {
            "messages": [HumanMessage(content="推荐一份医疗险")],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": "t-stream"}},
        stream_mode=["custom", "messages"],
        subgraphs=True,
    ):
        namespaces.add(namespace)
        if mode == "custom":
            token_text += payload.content if isinstance(payload.content, str) else ""
        else:
            chunk, meta = payload
            if isinstance(chunk, (AIMessage, AIMessageChunk)):
                ai_node_names.add(str(meta.get("langgraph_node")))
                if _is_model_node(meta):
                    final_message = _accumulate_model_message(final_message, chunk)

    assert token_text == "reply-from-insurance"
    assert final_message is not None
    if isinstance(final_message, AIMessageChunk):
        final_message = message_chunk_to_message(final_message)
    assert final_message.content == "reply-from-insurance"
    assert "model" in ai_node_names
    assert any(ns and ns[0].startswith("insurance_node:") for ns in namespaces)


@pytest.mark.asyncio
async def test_protocol_does_not_leak_across_checkpointed_intents():
    graph, models, classifier = _build_supervisor("general", checkpointer=InMemorySaver())
    await _invoke(graph, "解释报销流程", "t-protocol-switch", system_prompt="你是测试助手")

    classifier.intent = "chitchat"
    await graph.ainvoke(
        {"messages": [HumanMessage(content="你好呀")]},
        config={"configurable": {"thread_id": "t-protocol-switch"}},
    )

    system_messages = [m for m in models["chitchat"].captured[0] if m.type == "system"]
    assert system_messages[0].content == "你是测试助手"
    assert CHART_RESPONSE_PROTOCOL_PROMPT not in system_messages[0].content


@pytest.mark.asyncio
async def test_chat_sse_unpacks_subgraph_events_and_persists_final_message(monkeypatch):
    """锁定 API 对 subgraphs=True 三元事件及最终 AIMessageChunk 的处理。"""
    graph, _, _ = _build_supervisor("insurance")

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

    session = FakeSession()
    monkeypatch.setattr(chat_api, "Session", lambda _engine: session)

    frames = []
    async for frame in chat_api.stream_chat_response(
        thread_id="t-api-stream",
        model="fake-model",
        agent=graph,
        input_state={
            "messages": [HumanMessage(content="推荐一份医疗险")],
            "system_prompt": "你是测试助手",
        },
        config={"configurable": {"thread_id": "t-api-stream"}},
        last_user_content="推荐一份医疗险",
    ):
        frames.append(frame)

    payloads = [
        json.loads(frame.removeprefix("data: ").strip())
        for frame in frames
        if frame.startswith("data: {")
    ]
    assert not any(item.get("type") == "intent" for item in payloads)
    token_text = "".join(
        item["choices"][0]["delta"].get("content", "") for item in payloads if "choices" in item
    )
    assert token_text == "reply-from-insurance"
    assert session.committed is True
    assert [message.role for message in session.added] == ["user", "assistant"]
    assert session.added[-1].content == "reply-from-insurance"


@pytest.mark.asyncio
async def test_checkpointer_memory_across_turns():
    graph, _, _ = _build_supervisor("chitchat", checkpointer=InMemorySaver())
    config = {"configurable": {"thread_id": "t-memory"}}

    await _invoke(graph, "你好", "t-memory")
    # 第二轮只发新消息（与 chat.py 的增量发送方式一致），历史由 checkpointer 补全
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="我刚才说了什么")],
            "system_prompt": "你是测试助手",
        },
        config=config,
    )

    messages = result["messages"]
    assert len(messages) == 4  # u1 + a1 + u2 + a2
    assert messages[1].content == "reply-from-chitchat"
    assert messages[3].content == "reply-from-chitchat"
