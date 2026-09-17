"""plan_shows 筛选查询逻辑测试：匹配顺序、放宽与回退（SQLite 内存库）。"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models.plan_show import PlanShow
from app.services.plans.query import (
    list_distinct_titles,
    list_plan_shows_by_filter,
)


def _row(
    group_code: str,
    title: str,
    *,
    group_name: str | None = None,
    contents: str | None = None,
    title_ord: int = 1,
) -> PlanShow:
    return PlanShow(
        group_code=group_code,
        group_name=group_name or f"方案{group_code}",
        contents=contents or "基础保障说明",
        order_num=1,
        title_id=title_ord,
        title=title,
        title_ord_num=title_ord,
        has_sale="2",
        insur_list=["AYR"],
        is_more_insur=0,
        is_approve=1,
        is_irisk=2,
    )


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=[PlanShow.__table__])
    with Session(engine) as session:
        session.add_all(
            [
                _row("G1", "寿险", title_ord=1),
                _row("G2", "寿险", group_name="增额终身寿", title_ord=1),
                _row("G3", "健康", contents="重疾与医疗保障", title_ord=2),
                _row("G4", "年金", group_name="养老年金保险", contents="养老规划", title_ord=3),
                _row("G5", "万能", group_name="万能型两全保险", title_ord=4),
                _row("G6", "万能", contents="灵活缴费", title_ord=4),
            ]
        )
        session.commit()
        yield session


def test_distinct_titles_ordered(session):
    assert list_distinct_titles(session) == ["寿险", "健康", "年金", "万能"]


def test_empty_filter_returns_all(session):
    result = list_plan_shows_by_filter(session)
    assert result.mode == "all"
    assert result.matched_by is None
    assert len(result.rows) == 6
    assert result.available_titles == ["寿险", "健康", "年金", "万能"]


def test_category_match_returns_category_rows(session):
    result = list_plan_shows_by_filter(session, category="万能")
    assert result.mode == "filtered"
    assert result.matched_by == "category"
    assert [row.group_code for row in result.rows] == ["G5", "G6"]


def test_category_with_common_suffix_still_matches(session):
    """用户说「万能险」，分类是「万能」：双向包含应命中。"""
    result = list_plan_shows_by_filter(session, category="万能险")
    assert result.mode == "filtered"
    assert len(result.rows) == 2


def test_category_plus_keyword_narrows_within_category(session):
    result = list_plan_shows_by_filter(session, category="万能", keywords=["灵活"])
    assert result.mode == "filtered"
    assert result.matched_by == "category+keyword"
    assert [row.group_code for row in result.rows] == ["G6"]


def test_category_hit_but_keyword_miss_falls_back_to_category(session):
    """分类内关键词 0 命中时回退该分类全量，不藏掉整个分类。"""
    result = list_plan_shows_by_filter(session, category="万能", keywords=["分红"])
    assert result.mode == "filtered"
    assert result.matched_by == "category"
    assert len(result.rows) == 2


def test_unknown_category_relaxes_to_name_and_contents(session):
    """「重疾」不是分类，但健康方案的卖点里有「重疾」：放宽匹配命中。"""
    result = list_plan_shows_by_filter(session, category="重疾")
    assert result.mode == "filtered"
    assert result.matched_by == "keyword"
    assert [row.group_code for row in result.rows] == ["G3"]


def test_keywords_only_match_name_and_contents(session):
    result = list_plan_shows_by_filter(session, keywords=["养老"])
    assert result.mode == "filtered"
    assert result.matched_by == "keyword"
    assert {row.group_code for row in result.rows} == {"G4"}


def test_no_match_reports_available_titles(session):
    result = list_plan_shows_by_filter(session, category="车险")
    assert result.mode == "no_match"
    assert result.rows == []
    assert result.available_titles == ["寿险", "健康", "年金", "万能"]
