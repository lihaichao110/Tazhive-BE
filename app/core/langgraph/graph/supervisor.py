"""supervisor 图：意图识别节点 + 显式路由到各意图子 Agent。

图结构（新增意图时由注册表自动扩展，无需改本文件）：

    START → intent_node ──(conditional edges: state.intent)──┬─ chitchat_node  ─→ END
                                                             ├─ general_node   ─→ END
                                                             ├─ search_node    ─→ END
                                                             ├─ chart_analysis_node ─→ END
                                                             └─ insurance_node ─→ END

intent_node 每轮请求执行一次：调分类器 → 写 state.intent → 路由。
协议拼接由各意图 Agent 管线负责。
各意图处理节点由 agents/factory.py 构建；普通意图是 create_agent，search
是“规划 → Tavily → 回答”子图。它们直接挂载为图节点，以保留内部 token 流。
"""

from collections.abc import Hashable

from langchain_core.messages import HumanMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.core.langgraph.agents.factory import build_agent_for_intent
from app.core.langgraph.checkpointer import get_async_checkpointer
from app.core.langgraph.intent.classifier import (
    IntentClassifier,
    get_intent_classifier,
)
from app.core.langgraph.intent.registry import get_intent_spec, iterate_intent_specs
from app.core.langgraph.state import ChatAgentState
from app.core.logging import logger


class SupervisorState(ChatAgentState):
    """外层路由图状态；字段与意图子 Agent 的 ChatAgentState 完全兼容。"""


def _last_user_text(messages: list) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and msg.content:
            return msg.content if isinstance(msg.content, str) else str(msg.content)
    return None


def make_intent_node(classifier: IntentClassifier):
    """构建 intent_node：分类、归一化并写入路由状态。"""

    async def intent_node(state: SupervisorState) -> dict:
        text = _last_user_text(state.get("messages") or [])
        result = await classifier.classify(text or "")
        spec = get_intent_spec(result.intent)

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
    agent_builder=build_agent_for_intent,
    checkpointer=None,
):
    """编译 supervisor 图。classifier / agent_builder / checkpointer 均可注入，供测试使用。"""
    builder = StateGraph(SupervisorState)
    builder.add_node("intent_node", make_intent_node(classifier or get_intent_classifier()))

    route_map: dict[Hashable, str] = {}
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
