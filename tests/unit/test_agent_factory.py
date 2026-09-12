"""build_intent_agent 单元测试：按意图组装工具与中间件链。"""

from langchain_core.language_models.fake_chat_models import FakeChatModel

from app.core.langgraph.agents.factory import (
    _build_middleware_chain,
    _shared_metrics,
    _shared_model_routing,
    _shared_resilience,
    _shared_streaming,
    build_agent_for_intent,
    build_intent_agent,
)
from app.core.langgraph.intent.registry import get_intent_spec
from app.core.langgraph.middleware import (
    MetricsMiddleware,
    ModelRoutingMiddleware,
    RagMiddleware,
    ResilienceMiddleware,
    StreamingMiddleware,
)


class FakeRegistry:
    def get_model(self, model_name=None, thinking=None):
        return FakeChatModel()

    def rotate(self):
        pass


def test_chitchat_chain_has_no_rag():
    chain = _build_middleware_chain(get_intent_spec("chitchat"))

    assert len(chain) == 5  # dynamic_prompt + 4 个横切中间件
    assert not any(isinstance(mw, RagMiddleware) for mw in chain)


def test_general_chain_mounts_rag_between_metrics_and_resilience():
    chain = _build_middleware_chain(get_intent_spec("general"))

    assert len(chain) == 6
    rag_positions = [i for i, mw in enumerate(chain) if isinstance(mw, RagMiddleware)]
    assert rag_positions == [2], "Rag 应在 Metrics 内、Resilience 外（重试不重复检索）"
    assert isinstance(chain[1], MetricsMiddleware)
    assert isinstance(chain[3], ResilienceMiddleware)
    assert isinstance(chain[4], ModelRoutingMiddleware)
    assert isinstance(chain[5], StreamingMiddleware)


def test_search_chain_has_only_search_specific_tools_and_no_rag():
    spec = get_intent_spec("search")
    chain = _build_middleware_chain(spec)

    assert not any(isinstance(mw, RagMiddleware) for mw in chain)
    assert spec.tools is not None
    assert [tool.name for tool in spec.tools] == [
        "tavily_search",
        "get_current_time",
        "calculator",
    ]


def test_search_intent_uses_deterministic_search_subgraph():
    graph = build_agent_for_intent(get_intent_spec("search"))

    assert {"search_plan_node", "tavily_node", "search_answer_node"} <= set(
        graph.get_graph().nodes
    )


def test_shared_middleware_singletons_reused_across_intents():
    chain_a = _build_middleware_chain(get_intent_spec("chitchat"))
    chain_b = _build_middleware_chain(get_intent_spec("general"))

    assert chain_a[1] is chain_b[1] is _shared_metrics
    assert chain_a[-1] is chain_b[-1] is _shared_streaming
    # 未注入 registry 时，Resilience/ModelRouting 也使用共享单例
    assert any(mw is _shared_resilience for mw in chain_a)
    assert any(mw is _shared_model_routing for mw in chain_b)


def test_prompt_adapter_is_bound_to_each_intent_pipeline():
    chitchat_chain = _build_middleware_chain(get_intent_spec("chitchat"))
    general_chain = _build_middleware_chain(get_intent_spec("general"))

    # 提示词适配器携带各意图协议，因此不是共享横切中间件单例。
    assert chitchat_chain[0] is not general_chain[0]


def test_registry_injection_replaces_resilience_and_routing():
    registry = FakeRegistry()
    chain = _build_middleware_chain(get_intent_spec("general"), registry=registry)

    assert all(mw is not _shared_resilience for mw in chain)
    assert all(mw is not _shared_model_routing for mw in chain)
    injected_routing = [mw for mw in chain if isinstance(mw, ModelRoutingMiddleware)]
    assert injected_routing and injected_routing[0].registry is registry


def test_build_intent_agent_compiles_per_spec():
    agent = build_intent_agent(
        get_intent_spec("chitchat"),
        model=FakeChatModel(),
        registry=FakeRegistry(),
    )
    # create_agent 返回编译图，节点中应包含 model/tools（挂载进 supervisor 后共享 state）
    assert hasattr(agent, "ainvoke")
