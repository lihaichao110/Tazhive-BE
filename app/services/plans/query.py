"""方案展示（plan_shows）查询：为 insurance 意图提供在售方案数据与筛选。

筛选是确定性代码：上层（PlanFilterPlanner）只产出结构化条件（分类名/关键词），
匹配顺序 ①分类 title → ②方案名/卖点放宽匹配 → ③零命中，全部在服务端执行，
模型摸不到卡片数据。
"""

from dataclasses import dataclass, field
from typing import Literal

from sqlmodel import Session, select

from app.models.plan_show import PlanShow
from app.services.database import engine

MAX_PLAN_SHOW_ITEMS = 50
"""单轮下发的方案上限；当前源数据 25 条，留余量同时防止异常数据把卡片撑爆。"""

MatchMode = Literal["all", "filtered", "no_match"]


@dataclass
class PlanQueryResult:
    """一次方案查询的结果与命中信息，供子图节点决定卡片与回答上下文。"""

    rows: list[PlanShow] = field(default_factory=list)
    mode: MatchMode = "all"
    """all 泛化全量 / filtered 条件命中 / no_match 条件未命中。"""

    matched_by: str | None = None
    """filtered 时的命中方式：category / category+keyword / keyword。"""

    available_titles: list[str] = field(default_factory=list)
    """当前库里的全部分类名，零命中时引导用户用。"""


def list_distinct_titles(session: Session) -> list[str]:
    """按分类展示顺序返回去重后的分类名。

    已知有损点：源数据中无方案的分类（如「组合」）不会出现在 plan_shows 里，
    该分类会被漏掉；用于零命中引导时可接受，前端 tab 列表另有兜底。
    """
    rows = session.exec(
        select(PlanShow.title, PlanShow.title_ord_num)
        .distinct()  # type: ignore[union-attr]
        .order_by("title_ord_num")
    ).all()
    return [row[0] for row in rows]


def _category_matches(title: str, category: str) -> bool:
    """双向包含：用户说「万能险」也能命中分类「万能」，反之亦然。"""
    return category in title or title in category


def _keyword_matches(row: PlanShow, keywords: list[str]) -> bool:
    haystacks = (row.group_name or "") + "\n" + (row.contents or "")
    return any(keyword in haystacks for keyword in keywords if keyword)


def list_plan_shows(session: Session, limit: int = MAX_PLAN_SHOW_ITEMS) -> list[PlanShow]:
    """按「分类顺序 + 分类内顺序」返回方案。

    不按 has_sale 过滤：源数据中该字段 1/2 的语义尚未确认，全量下发并把原始值
    随卡片透传给前端，由前端决定是否置灰或打标。
    """
    # 字符串列名排序：SQLModel 给 Field() 属性的类级类型是 int，传列对象 mypy 会
    # 报 arg-type（与 messages.py 的排序写法一致）
    statement = select(PlanShow).order_by("title_ord_num", "order_num").limit(limit)
    return list(session.exec(statement).all())


def list_plan_shows_by_filter(
    session: Session,
    *,
    category: str | None = None,
    keywords: list[str] | None = None,
    limit: int = MAX_PLAN_SHOW_ITEMS,
) -> PlanQueryResult:
    """按结构化条件筛选方案；条件全空时退回泛化全量。

    匹配顺序：
    1. category 与分类 title 双向包含 → 该分类全部（若同时给了 keywords 且分类内
       有命中，则进一步收窄；分类内 0 命中时回退该分类全量——分类是强信号，
       不因卖点文案没提到关键词就藏掉整个分类）。
    2. category 未命中分类时，放宽为 category/keywords 任一词在方案名或卖点中包含。
    3. 仍无命中 → no_match。
    """
    titles = list_distinct_titles(session)
    category = (category or "").strip() or None
    cleaned_keywords = [kw.strip() for kw in (keywords or []) if kw and kw.strip()]

    if not category and not cleaned_keywords:
        return PlanQueryResult(
            rows=list_plan_shows(session, limit),
            mode="all",
            available_titles=titles,
        )

    all_rows = list_plan_shows(session, limit)

    if category:
        category_rows = [row for row in all_rows if _category_matches(row.title, category)]
        if category_rows:
            if cleaned_keywords:
                narrowed = [row for row in category_rows if _keyword_matches(row, cleaned_keywords)]
                if narrowed:
                    return PlanQueryResult(
                        rows=narrowed,
                        mode="filtered",
                        matched_by="category+keyword",
                        available_titles=titles,
                    )
            return PlanQueryResult(
                rows=category_rows,
                mode="filtered",
                matched_by="category",
                available_titles=titles,
            )

    relaxed_terms = ([category] if category else []) + cleaned_keywords
    relaxed_rows = [row for row in all_rows if _keyword_matches(row, relaxed_terms)]
    if relaxed_rows:
        return PlanQueryResult(
            rows=relaxed_rows,
            mode="filtered",
            matched_by="keyword",
            available_titles=titles,
        )

    return PlanQueryResult(rows=[], mode="no_match", available_titles=titles)


def _extract_filter_terms(plan_filter: dict | None) -> tuple[str | None, list[str]]:
    """从子图 state 里的筛选条件 dict 取 (category, keywords)；异常输入按泛化处理。"""
    if not isinstance(plan_filter, dict):
        return None, []
    category = plan_filter.get("category")
    keywords = plan_filter.get("keywords")
    return (
        str(category) if category else None,
        [str(kw) for kw in keywords] if isinstance(keywords, list) else [],
    )


def fetch_plan_shows(plan_filter: dict | None = None) -> PlanQueryResult:
    """自建会话查询，供没有 FastAPI 会话依赖的调用方（如意图子图节点）使用。

    plan_filter 为 None 或空条件时等价于原来的全量查询。
    """
    category, keywords = _extract_filter_terms(plan_filter)
    with Session(engine) as session:
        return list_plan_shows_by_filter(session, category=category, keywords=keywords)


def fetch_plan_titles() -> list[str]:
    """自建会话查询分类列表，供筛选条件提取的提示词使用。"""
    with Session(engine) as session:
        return list_distinct_titles(session)
