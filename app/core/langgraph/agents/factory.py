"""按意图配置构建子 Agent 的工厂。

普通意图使用 create_agent：工厂把请求级基础提示词与该意图的协议拼接，
并按 IntentSpec 组装工具集与中间件链。search 与 insurance 意图使用各自的
确定性服务端子图（联网搜索 / 查库出卡片）。
横切中间件（指标/重试/模型路由/流式）使用模块级单例；RagMiddleware
只挂载到 use_rag 的意图上。
"""

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_core.language_models import BaseChatModel

from app.core.langgraph.intent.registry import IntentSpec
from app.core.langgraph.middleware import (
    MetricsMiddleware,
    ModelRoutingMiddleware,
    RagMiddleware,
    ResilienceMiddleware,
    StreamingMiddleware,
)
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from app.core.langgraph.state import ChatAgentState
from app.core.langgraph.tools import tools as default_tools
from app.services.llm.registry import LLMRegistry, default_registry


def _make_system_prompt_middleware(spec: IntentSpec):
    """创建绑定到单个意图管线的提示词适配器。

    state.system_prompt 始终保留请求的基础身份提示词，协议只在模型调用前拼接，
    避免 checkpoint 中上一轮的协议泄漏到新一轮意图。
    """

    @dynamic_prompt
    def system_prompt_from_state(request) -> str:
        base_prompt = request.state.get("system_prompt") or SYSTEM_CHAT_PROMPT
        if not spec.protocol_prompt:
            return base_prompt
        return f"{base_prompt.rstrip()}\n\n{spec.protocol_prompt}"

    return system_prompt_from_state


# 共享横切中间件单例：无状态或仅持有全局 registry，可安全跨 Agent 复用
_shared_metrics = MetricsMiddleware()
_shared_resilience = ResilienceMiddleware()
_shared_model_routing = ModelRoutingMiddleware()
_shared_streaming = StreamingMiddleware()


def _build_middleware_chain(spec: IntentSpec, registry: LLMRegistry | None = None) -> list:
    """按意图组装中间件链（列表靠前为外层）。

    Metrics → Rag(仅 use_rag) → Resilience → ModelRouting → Streaming；
    Rag 放 Resilience 外层，模型重试时不重复检索。
    """
    if registry is not None:
        resilience = ResilienceMiddleware(registry=registry)
        model_routing = ModelRoutingMiddleware(registry=registry)
    else:
        resilience = _shared_resilience
        model_routing = _shared_model_routing

    # 提示词适配器属于意图管线本身，不属于四个共享横切中间件。
    middleware: list = [_make_system_prompt_middleware(spec), _shared_metrics]
    if spec.use_rag:
        middleware.append(RagMiddleware())
    middleware += [resilience, model_routing, _shared_streaming]
    return middleware


def build_intent_agent(
    spec: IntentSpec,
    *,
    model: BaseChatModel | None = None,
    registry: LLMRegistry | None = None,
):
    """构建单个意图的子 Agent（编译后的 create_agent 图）。

    model/registry 仅用于测试注入；生产路径由 ModelRoutingMiddleware
    在每次调用时按请求 state 覆盖模型实例。
    """
    return create_agent(
        model=model if model is not None else default_registry.get_model(),
        tools=spec.tools if spec.tools is not None else default_tools,
        middleware=_build_middleware_chain(spec, registry),
        state_schema=ChatAgentState,
        # checkpointer 挂在 supervisor 外层图上，子 Agent 不单独持久化
    )


def build_agent_for_intent(spec: IntentSpec):
    """按意图选择执行管线；search / insurance 使用确定性服务端子图，其余沿用通用 Agent。"""
    if spec.id == "search":
        # 延迟导入避免子图复用本模块中间件工厂时产生循环依赖。
        from app.core.langgraph.agents.search import build_search_agent

        return build_search_agent(spec)
    if spec.id == "insurance":
        # 同上：查库出卡片是服务端确定性步骤，不能让模型自由发挥。
        from app.core.langgraph.agents.insurance import build_insurance_agent

        return build_insurance_agent(spec)
    return build_intent_agent(spec)
