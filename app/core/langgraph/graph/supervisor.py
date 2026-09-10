"""supervisor 图：意图识别节点 + 显式路由到各意图子 Agent。

图结构（新增意图时由注册表自动扩展，无需改本文件）：

    START → intent_node ──(conditional edges: state.intent)──┬─ chitchat_node  ─→ END
                                                             ├─ general_node   ─→ END
                                                             ├─ chart_analysis_node ─→ END
                                                             └─ insurance_node ─→ END

intent_node 每轮请求执行一次：调分类器 → 写 state.intent → 通过
stream_writer 向前端广播意图事件。协议拼接由各意图 Agent 管线负责。
各子 Agent 节点是 create_agent 编译图（agents/factory.py 构建），直接挂载
为图节点以保留其内部 token 流（custom 事件沿子图冒泡到顶层 astream）。
"""

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import var_child_runnable_config
from langgraph.config import CONFIG_KEY_RUNTIME
from langgraph.constants import CONF, END, START
from langgraph.graph import StateGraph

from app.core.langgraph.agents.factory import build_intent_agent
from app.core.langgraph.checkpointer import get_async_checkpointer
from app.core.langgraph.intent.classifier import (
    IntentClassifier,
    get_intent_classifier,
)
from app.core.langgraph.intent.registry import get_intent_spec, iterate_intent_specs
from app.core.langgraph.middleware.streaming import _ensure_config_context
from app.core.langgraph.state import ChatAgentState
from app.core.logging import logger


class SupervisorState(ChatAgentState):
    """外层路由图状态；字段与意图子 Agent 的 ChatAgentState 完全兼容。"""


def _last_user_text(messages: list) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and msg.content:
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return None


def _broadcast(writer, payload: dict) -> None:
    """向顶层 custom 流广播事件；Python 3.10 下需先补 config contextvar
    （writer 内部会 get_config 取 checkpoint_ns，与 StreamingMiddleware 注释的
    是同一处上游断链，详见 streaming.py）。"""
    token = _ensure_config_context()
    try:
        if writer is not None:
            writer(payload)
    except Exception:
        pass
    finally:
        if token is not None:
            var_child_runnable_config.reset(token)


def make_intent_node(classifier: IntentClassifier):
    """构建 intent_node：分类、归一化并广播意图事件。"""

    async def intent_node(state: SupervisorState, config: RunnableConfig) -> dict:
        text = _last_user_text(state.get("messages") or [])
        result = await classifier.classify(text or "")
        spec = get_intent_spec(result.intent)

        # 意图事件尽力广播（ainvoke 等非流式调用下没有 writer，忽略即可）
        runtime = config.get(CONF, {}).get(CONFIG_KEY_RUNTIME)
        _broadcast(
            getattr(runtime, "stream_writer", None),
            {
                "type": "intent",
                "intent": spec.id,
                "confidence": result.confidence,
            },
        )

        logger.info(f"意图识别：{spec.id}（confidence={result.confidence}）")
        return {
            "intent": spec.id,
            "intent_confidence": result.confidence,
        }

    return intent_node


def route_by_intent(state: SupervisorState) -> str:
    """条件路由函数：返回意图 id，经 route_map 映射到对应子 Agent 节点。"""
    return get_intent_spec(state.get("intent")).id


def build_supervisor_graph(
    *,
    classifier: IntentClassifier | None = None,
    agent_builder=build_intent_agent,
    checkpointer=None,
):
    """编译 supervisor 图。classifier / agent_builder / checkpointer 均可注入，供测试使用。"""
    builder = StateGraph(SupervisorState)
    builder.add_node("intent_node", make_intent_node(classifier or get_intent_classifier()))

    route_map: dict[str, str] = {}
    for spec in iterate_intent_specs():
        node_name = f"{spec.id}_node"
        builder.add_node(node_name, agent_builder(spec))
        builder.add_edge(node_name, END)
        route_map[spec.id] = node_name

    builder.add_edge(START, "intent_node")
    builder.add_conditional_edges("intent_node", route_by_intent, route_map)
    return builder.compile(checkpointer=checkpointer)


_graph = None


async def get_supervisor_graph():
    """构建并缓存 supervisor 编译图（进程内单例，checkpointer 挂在外层图）。"""
    global _graph
    if _graph is None:
        checkpointer = await get_async_checkpointer()
        _graph = build_supervisor_graph(checkpointer=checkpointer)
        logger.info("supervisor 图编译完成（意图识别 + 按注册表路由子 Agent）")
    return _graph
