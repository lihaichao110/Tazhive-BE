"""确定性保险方案子图：先提取筛选条件，再查库出卡，最后生成说明。

与 search.py 同构：进入 insurance 意图后先由轻量模型把用户语言提取成
结构化筛选条件（PlanFilterPlanner，json_mode，失败降级为泛化），服务端按
条件确定性过滤 plan_shows（app/services/plans/query.py）——卡片数据仍然
完全由数据库行构造、不经过模型，避免模型编造产品与保费；模型只负责那句
自然语言说明（协议见 prompts/system_chat.py 的 INSURANCE_PROTOCOL_PROMPT）。
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any, Protocol
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.langgraph.agents.factory import _build_middleware_chain
from app.core.langgraph.agents.search import _recent_user_texts
from app.core.langgraph.intent.registry import IntentSpec
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from app.core.langgraph.state import InsuranceAgentState
from app.core.langgraph.tools import tools as default_tools
from app.core.logging import logger
from app.services.llm.registry import LLMRegistry, default_registry
from app.services.plans import (
    PLAN_CARD_COMPONENT,
    PlanQueryResult,
    build_plan_card_envelope,
    fetch_plan_shows,
    fetch_plan_titles,
)

PLAN_SURFACE_PREFIX = "insurance_plans"
"""surfaceId 前缀；每轮拼随机后缀，避免同一会话多张卡片撞 surfaceId 互相覆盖。"""

PLAN_FILTER_MODEL = "deepseek-v4-flash"
PLAN_FILTER_TIMEOUT_SECONDS = 8.0


class PlanFilter(BaseModel):
    """从用户语言提取的方案筛选条件；全空表示泛化请求（全量下发）。"""

    category: str | None = Field(
        default=None,
        max_length=20,
        description="用户明确提到的方案分类，如 寿险/健康/年金/万能；没提则为 null",
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="其他偏好关键词（人群/功能），如 父母、养老、分红、医疗；没有则为空数组",
    )


class PlanFilterPlannerProtocol(Protocol):
    async def aplan(self, messages: list, *, available_titles: list[str]) -> PlanFilter: ...


class PlanFilterPlanner:
    """使用轻量模型提取筛选条件；失败由调用节点降级为泛化（全量）。"""

    def __init__(self, model=None, timeout_seconds: float = PLAN_FILTER_TIMEOUT_SECONDS):
        planner_model = model or default_registry.get_model(
            PLAN_FILTER_MODEL,
            thinking={"type": "disabled"},
        )
        self._structured = planner_model.with_structured_output(PlanFilter, method="json_mode")
        self._timeout_seconds = timeout_seconds

    async def aplan(self, messages: list, *, available_titles: list[str]) -> PlanFilter:
        recent_texts = _recent_user_texts(messages)
        schema = json.dumps(PlanFilter.model_json_schema(), ensure_ascii=False)
        titles_text = "、".join(available_titles) or "（暂无）"
        prompt = (
            "你是保险方案筛选条件提取器。根据用户最近的消息提取结构化筛选条件，"
            "只做提取，不回答问题、不推荐产品。\n"
            f"当前在售方案的分类只有：{titles_text}。\n"
            "规则：\n"
            "1. 用户明确提到某个分类或其俗称（如「万能险」「寿险」）时填 category，"
            "尽量使用与分类列表一致的名字；提到的词与分类名不完全一致也没关系，照实填。\n"
            "2. 用户提到人群、功能、偏好（如 给父母、养老、分红、预算）时放进 keywords。\n"
            "3. 用户只是泛泛咨询（如「有什么保险推荐」）时，category 填 null、keywords 留空。\n"
            "4. 上一条用户消息是当前问题，之前几条供理解指代（可能包含此前追问的回答）。\n"
            f"输出必须符合以下 JSON Schema：\n{schema}\n"
            f"最近用户消息：{json.dumps(recent_texts, ensure_ascii=False)}"
        )
        result = await asyncio.wait_for(
            self._structured.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=recent_texts[-1] if recent_texts else "保险咨询"),
                ]
            ),
            timeout=self._timeout_seconds,
        )
        if not isinstance(result, PlanFilter):
            result = PlanFilter.model_validate(result)
        return result


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


def _describe_filter(plan_filter: dict[str, Any] | None, matched_by: str | None) -> str:
    """把筛选条件与命中方式拼成一句话口径，供回答模型的系统提示使用。"""
    category = plan_filter.get("category") if isinstance(plan_filter, dict) else None
    keywords = (plan_filter.get("keywords") if isinstance(plan_filter, dict) else None) or []
    parts: list[str] = []
    if matched_by in ("category", "category+keyword") and category:
        parts.append(f"分类「{category}」")
    if matched_by in ("category+keyword", "keyword"):
        # 放宽命中时，分类词是作为关键词在方案名/卖点里匹配上的，一并说明
        terms = ([category] if category else []) + [str(kw) for kw in keywords]
        if terms:
            parts.append(f"关键词「{'、'.join(terms)}」")
    if not parts:
        parts.append("用户提出的条件")
    return "按" + " + ".join(parts) + "筛选"


def _format_plan_context(state: InsuranceAgentState) -> str:
    """把本轮筛选与卡片下发情况注入系统提示，避免模型承诺了卡片却没有卡。"""
    raw_match = state.get("plan_match")
    match: dict[str, Any] = raw_match if isinstance(raw_match, dict) else {}
    mode = match.get("mode")

    envelope = state.get("x_card")
    if isinstance(envelope, dict):
        total = _count_plan_cards(envelope)
        if mode == "filtered":
            scope = _describe_filter(state.get("plan_filter"), match.get("matched_by"))
            return (
                f"服务端已{scope}在售方案，并下发了 {total} 张匹配卡片（卡片含「预核保」"
                "「正式投保」按钮），用户界面已经展示。说明时交代筛选口径，"
                "不要重复罗列产品名称与卖点，可基于结果继续给选品方向或追问。"
            )
        return (
            f"服务端已查询在售方案并下发了 {total} 张卡片（卡片含「预核保」「正式投保」按钮），"
            "用户界面已经展示，不要重复罗列产品名称与卖点。"
        )

    if mode == "no_match":
        titles = "、".join(match.get("available_titles") or []) or "（分类列表不可用）"
        return (
            f"服务端已按用户提出的条件筛选在售方案，但没有匹配到任何方案，本轮未下发卡片。"
            f"当前在售方案的分类有：{titles}。请如实告知没有匹配到，"
            "引导用户从现有分类中选择或放宽条件；不要编造产品名称与保费。"
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
    filter_planner: PlanFilterPlannerProtocol | None = None,
    plan_loader: Callable[[dict[str, Any] | None], PlanQueryResult] = fetch_plan_shows,
    titles_loader: Callable[[], list[str]] = fetch_plan_titles,
    answer_model: BaseChatModel | None = None,
    registry: LLMRegistry | None = None,
):
    """构建 insurance 专属子图：提取筛选条件 → 查库出卡片 → 生成自然语言说明。"""
    planner = filter_planner or PlanFilterPlanner()

    async def plan_filter_node(state: InsuranceAgentState) -> dict[str, Any]:
        try:
            titles = titles_loader()
            plan_filter = await planner.aplan(state.get("messages") or [], available_titles=titles)
            logger.info(
                "方案筛选条件提取完成：category=%s keywords=%s",
                plan_filter.category,
                plan_filter.keywords,
            )
        except Exception as exc:
            # 提取失败不打断本轮：降级为泛化全量，行为与改造前一致
            logger.warning(
                "方案筛选条件提取失败，本轮按泛化全量下发：error_type=%s", type(exc).__name__
            )
            plan_filter = PlanFilter()
        return {"plan_filter": plan_filter.model_dump()}

    async def plan_query_node(state: InsuranceAgentState) -> dict[str, Any]:
        surface_id = f"{PLAN_SURFACE_PREFIX}_{uuid4().hex[:8]}"
        try:
            query_result = await asyncio.to_thread(plan_loader, state.get("plan_filter"))
        except Exception as exc:
            # 查询失败不打断本轮：降级为纯文本回复，由提示词如实告知用户
            logger.warning("保险方案查询失败，本轮只回文本：error_type=%s", type(exc).__name__)
            return {"x_card": None, "plan_match": {"mode": "error"}}
        plan_match = {
            "mode": query_result.mode,
            "matched_by": query_result.matched_by,
            "count": len(query_result.rows),
            "available_titles": query_result.available_titles,
        }
        if not query_result.rows:
            logger.info("保险方案查询完成：无匹配方案 mode=%s", query_result.mode)
            return {"x_card": None, "plan_match": plan_match}
        envelope = build_plan_card_envelope(
            query_result.rows,
            surface_id=surface_id,
            catalog_id=settings.plan_show_catalog_id,
        )
        if envelope is None:
            logger.info("保险方案查询完成：没有可下发的在售方案")
            return {"x_card": None, "plan_match": plan_match}
        logger.info(
            "保险方案卡片已生成：surface_id=%s cards=%s mode=%s matched_by=%s",
            surface_id,
            _count_plan_cards(envelope),
            query_result.mode,
            query_result.matched_by,
        )
        return {"x_card": envelope, "plan_match": plan_match}

    answer_middleware = _build_middleware_chain(spec, registry)
    # 替换通用动态提示词：把卡片下发情况注入，其余中间件链保持与其他意图一致
    answer_middleware[0] = _make_insurance_answer_prompt(spec)
    answer_agent = create_agent(
        model=(answer_model if answer_model is not None else default_registry.get_model()),
        tools=spec.tools if spec.tools is not None else default_tools,
        middleware=answer_middleware,
        state_schema=InsuranceAgentState,
    )

    builder = StateGraph(InsuranceAgentState)
    builder.add_node("plan_filter_node", plan_filter_node)
    builder.add_node("plan_query_node", plan_query_node)
    builder.add_node("insurance_answer_node", answer_agent)
    builder.add_edge(START, "plan_filter_node")
    builder.add_edge("plan_filter_node", "plan_query_node")
    builder.add_edge("plan_query_node", "insurance_answer_node")
    builder.add_edge("insurance_answer_node", END)
    return builder.compile()


__all__ = ["PLAN_SURFACE_PREFIX", "PlanFilter", "PlanFilterPlanner", "build_insurance_agent"]
