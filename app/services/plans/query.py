"""方案展示（plan_shows）查询：为 insurance 意图提供在售方案数据。"""

from sqlmodel import Session, select

from app.models.plan_show import PlanShow
from app.services.database import engine

MAX_PLAN_SHOW_ITEMS = 50
"""单轮下发的方案上限；当前源数据 25 条，留余量同时防止异常数据把卡片撑爆。"""


def list_plan_shows(session: Session, limit: int = MAX_PLAN_SHOW_ITEMS) -> list[PlanShow]:
    """按「分类顺序 + 分类内顺序」返回方案。

    不按 has_sale 过滤：源数据中该字段 1/2 的语义尚未确认，全量下发并把原始值
    随卡片透传给前端，由前端决定是否置灰或打标。
    """
    # 字符串列名排序：SQLModel 给 Field() 属性的类级类型是 int，传列对象 mypy 会
    # 报 arg-type（与 messages.py 的排序写法一致）
    statement = select(PlanShow).order_by("title_ord_num", "order_num").limit(limit)
    return list(session.exec(statement).all())


def fetch_plan_shows(limit: int = MAX_PLAN_SHOW_ITEMS) -> list[PlanShow]:
    """自建会话查询，供没有 FastAPI 会话依赖的调用方（如意图子图节点）使用。"""
    with Session(engine) as session:
        return list_plan_shows(session, limit=limit)
