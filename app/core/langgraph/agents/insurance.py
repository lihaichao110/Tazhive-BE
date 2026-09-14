"""确定性保险方案子图：查 plan_shows 生成 A2UI 卡片，再由模型写一句说明。

与 search.py 同构：进入 insurance 意图后必定执行一次服务端查询，卡片数据
完全由数据库行构造、不经过模型，避免模型编造产品与保费；模型只负责那句
自然语言说明（协议见 prompts/system_chat.py 的 INSURANCE_PROTOCOL_PROMPT）。
"""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_core.language_models import BaseChatModel
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.core.config import settings
from app.core.langgraph.agents.factory import _build_middleware_chain
from app.core.langgraph.intent.registry import IntentSpec
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from app.core.langgraph.state import ChatAgentState
from app.core.langgraph.tools import tools as default_tools
from app.core.logging import logger
from app.models.plan_show import PlanShow
from app.services.llm.registry import LLMRegistry, default_registry
from app.services.plans import PLAN_CARD_COMPONENT, build_plan_card_envelope, fetch_plan_shows

PLAN_SURFACE_PREFIX = "insurance_plans"
"""surfaceId 前缀；每轮拼随机后缀，避免同一会话多张卡片撞 surfaceId 互相覆盖。"""


def _count_plan_cards(envelope: dict[str, Any]) -> int:
    """从信封的 updateComponents 里数出方案卡组件数量。"""
    for command in envelope.get("commands") or []:
        payload = command.get("updateComponents")
        if not payload:
            continue
        return sum(
            1
            for item in payload.get("components") or []
            if item.get("component") == PLAN_CARD_COMPONENT
        )
    return 0


def _format_plan_context(state: ChatAgentState) -> str:
    """把本轮卡片下发情况注入系统提示，避免模型承诺了卡片却没有卡。"""
    envelope = state.get("x_card")
    if isinstance(envelope, dict):
        total = _count_plan_cards(envelope)
        return (
            f"服务端已查询在售方案并下发了 {total} 张卡片（卡片含「预核保」「正式投保」按钮），"
            "用户界面已经展示，不要重复罗列产品名称与卖点。"
        )
    return (
        "服务端本轮未取到在售方案数据（查询失败或当前没有在售方案）。"
        "请如实告知用户暂时无法展示产品列表，建议稍后重试或联系人工顾问；"
        "不要凭记忆编造产品名称与保费。"
    )


def _make_insurance_answer_prompt(spec: IntentSpec):
    """把卡片下发情况动态注入系统提示；卡片数据本身不进模型上下文。"""

    @dynamic_prompt
    def insurance_answer_prompt(request) -> str:
        base_prompt = request.state.get("system_prompt") or SYSTEM_CHAT_PROMPT
        protocol = spec.protocol_prompt or ""
        context = _format_plan_context(request.state)
        return f"{base_prompt.rstrip()}\n\n{protocol}\n\n{context}"

    return insurance_answer_prompt


def build_insurance_agent(
    spec: IntentSpec,
    *,
    plan_loader: Callable[[], list[PlanShow]] = fetch_plan_shows,
    answer_model: BaseChatModel | None = None,
    registry: LLMRegistry | None = None,
):
    """构建 insurance 专属子图：先查库出卡片，再生成自然语言说明。"""

    async def plan_query_node(state: ChatAgentState) -> dict[str, Any]:
        surface_id = f"{PLAN_SURFACE_PREFIX}_{uuid4().hex[:8]}"
        try:
            rows = plan_loader()
            envelope = build_plan_card_envelope(
                rows,
                surface_id=surface_id,
                catalog_id=settings.plan_show_catalog_id,
            )
        except Exception as exc:
            # 查询失败不打断本轮：降级为纯文本回复，由提示词如实告知用户
            logger.warning("保险方案查询失败，本轮只回文本：error_type=%s", type(exc).__name__)
            return {"x_card": None}
        if envelope is None:
            logger.info("保险方案查询完成：没有可下发的在售方案")
            return {"x_card": None}
        logger.info(
            "保险方案卡片已生成：surface_id=%s cards=%s",
            surface_id,
            _count_plan_cards(envelope),
        )
        return {"x_card": envelope}

    answer_middleware = _build_middleware_chain(spec, registry)
    # 替换通用动态提示词：把卡片下发情况注入，其余中间件链保持与其他意图一致
    answer_middleware[0] = _make_insurance_answer_prompt(spec)
    answer_agent = create_agent(
        model=(answer_model if answer_model is not None else default_registry.get_model()),
        tools=spec.tools if spec.tools is not None else default_tools,
        middleware=answer_middleware,
        state_schema=ChatAgentState,
    )

    builder = StateGraph(ChatAgentState)
    builder.add_node("plan_query_node", plan_query_node)
    builder.add_node("insurance_answer_node", answer_agent)
    builder.add_edge(START, "plan_query_node")
    builder.add_edge("plan_query_node", "insurance_answer_node")
    builder.add_edge("insurance_answer_node", END)
    return builder.compile()


__all__ = ["PLAN_SURFACE_PREFIX", "build_insurance_agent"]
