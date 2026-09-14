"""plan_shows → A2UI v0.9 卡片信封的单元测试：命令结构、组件引用、按钮契约。"""

import json

import pytest
from sqlmodel import Session, create_engine

from app.models.plan_show import PlanShow
from app.services.plans import build_plan_card_envelope, list_plan_shows
from app.services.plans.x_card import (
    A2UI_VERSION,
    APPLY_ACTION_NAME,
    APPLY_BUTTON_COLOR,
    APPLY_BUTTON_TEXT,
    PLAN_CARD_COMPONENT,
    PRE_UNDERWRITE_ACTION_NAME,
    PRE_UNDERWRITE_BUTTON_COLOR,
    PRE_UNDERWRITE_BUTTON_TEXT,
    format_a2ui_fence,
)

SURFACE_ID = "insurance_plans_abcd1234"
CATALOG_ID = "https://a2ui.org/specification/v0_9/basic_catalog.json"


def _row(**overrides) -> PlanShow:
    """构造一行方案数据；默认值覆盖全部 NOT NULL 字段。"""
    values = {
        "group_code": "G0264",
        "group_name": "鸿利悠享2.0两全保险（分红型）",
        "contents": "幸福晚年加厚度\r\n健康保障有力度",
        "order_num": 1047,
        "title_id": 1,
        "title": "寿险",
        "title_ord_num": 1,
        "img": "https://example.com/a.png",
        "has_sale": "2",
        "insur_list": ["AYR", "AYS"],
        "is_more_insur": 0,
        "is_approve": 1,
        "is_irisk": 2,
    }
    values.update(overrides)
    return PlanShow(**values)


def _components(envelope) -> list[dict]:
    for command in envelope["commands"]:
        if "updateComponents" in command:
            return command["updateComponents"]["components"]
    raise AssertionError("信封里没有 updateComponents 命令")


def _component(envelope, component_id) -> dict:
    for item in _components(envelope):
        if item["id"] == component_id:
            return item
    raise AssertionError(f"找不到组件 {component_id}")


def _envelope(rows) -> dict:
    envelope = build_plan_card_envelope(rows, surface_id=SURFACE_ID, catalog_id=CATALOG_ID)
    assert envelope is not None
    return envelope


@pytest.mark.parametrize("rows", [[_row()], [_row(), _row(group_code="G0208", order_num=1072)]])
def test_every_command_carries_version_and_surface(rows):
    envelope = _envelope(rows)

    assert envelope["surfaceId"] == SURFACE_ID
    assert [
        next(key for key in command if key != "version") for command in envelope["commands"]
    ] == [
        "createSurface",
        "updateComponents",
        "updateDataModel",
    ]
    for command in envelope["commands"]:
        assert command["version"] == A2UI_VERSION
        payload = command[next(key for key in command if key != "version")]
        assert payload["surfaceId"] == SURFACE_ID


def test_create_surface_carries_catalog_id():
    envelope = _envelope([_row()])

    assert envelope["commands"][0]["createSurface"] == {
        "surfaceId": SURFACE_ID,
        "catalogId": CATALOG_ID,
    }


def test_component_tree_is_flat_adjacency_list_with_single_root():
    envelope = _envelope([_row(), _row(group_code="G0208", group_name="顺意百分百2025定期寿险")])
    components = _components(envelope)

    roots = [item for item in components if item["id"] == "root"]
    assert len(roots) == 1
    assert roots[0]["component"] == "PlanList"
    assert roots[0]["children"] == ["plan_G0264", "plan_G0208"]

    # 扁平邻接表：children 只能是 id 字符串，且引用的组件必须存在且 id 唯一
    ids = [item["id"] for item in components]
    assert len(set(ids)) == len(ids)
    for item in components:
        assert isinstance(item["component"], str)
        assert all(isinstance(child, str) for child in item.get("children") or [])
        assert set(item.get("children") or []) <= set(ids)


def test_card_carries_business_fields_and_children_in_fixed_order():
    envelope = _envelope([_row()])

    card = _component(envelope, "plan_G0264")
    assert card["component"] == PLAN_CARD_COMPONENT
    assert card["groupCode"] == "G0264"
    assert card["groupName"] == "鸿利悠享2.0两全保险（分红型）"
    assert card["title"] == "寿险"
    assert card["hasSale"] == "2"
    assert card["children"] == ["plan_G0264_img", "plan_G0264_points", "plan_G0264_act"]

    assert _component(envelope, "plan_G0264_img") == {
        "id": "plan_G0264_img",
        "component": "PlanImage",
        "url": "https://example.com/a.png",
        "altText": "鸿利悠享2.0两全保险（分红型）",
    }
    assert _component(envelope, "plan_G0264_points")["items"] == [
        "幸福晚年加厚度",
        "健康保障有力度",
    ]
    assert _component(envelope, "plan_G0264_act")["children"] == [
        "plan_G0264_pre",
        "plan_G0264_apply",
    ]


def test_buttons_carry_colors_and_literal_action_context():
    envelope = _envelope([_row()])

    pre = _component(envelope, "plan_G0264_pre")
    assert pre["text"] == PRE_UNDERWRITE_BUTTON_TEXT
    assert pre["backgroundColor"] == PRE_UNDERWRITE_BUTTON_COLOR
    assert pre["color"] == "#ffffff"
    assert pre["borderRadius"] == "6px"
    assert pre["action"]["event"]["name"] == PRE_UNDERWRITE_ACTION_NAME

    apply_button = _component(envelope, "plan_G0264_apply")
    assert apply_button["text"] == APPLY_BUTTON_TEXT
    assert apply_button["backgroundColor"] == APPLY_BUTTON_COLOR
    assert apply_button["action"]["event"]["name"] == APPLY_ACTION_NAME

    # context 是字面量（而非 {"path": ...}），前端 onAction 里可直取值
    assert pre["action"]["event"]["context"] == {
        "group_code": "G0264",
        "group_name": "鸿利悠享2.0两全保险（分红型）",
        "title": "寿险",
        "insur_list": ["AYR", "AYS"],
    }
    assert pre["action"]["event"]["context"] == apply_button["action"]["event"]["context"]


def test_points_split_only_crlf_lines_and_skip_blanks():
    envelope = _envelope([_row(contents="\r\n卖点一\r\n\r\n卖点二\n卖点三\r\n")])

    assert _component(envelope, "plan_G0264_points")["items"] == ["卖点一", "卖点二", "卖点三"]


BASE_IDS = {"root", "plan_G0264", "plan_G0264_act", "plan_G0264_pre", "plan_G0264_apply"}


@pytest.mark.parametrize(
    ("overrides", "expected_children", "expected_ids"),
    [
        ({"img": None}, ["plan_G0264_points", "plan_G0264_act"], BASE_IDS | {"plan_G0264_points"}),
        ({"contents": None}, ["plan_G0264_img", "plan_G0264_act"], BASE_IDS | {"plan_G0264_img"}),
        (
            {"contents": "  \r\n \r\n"},
            ["plan_G0264_img", "plan_G0264_act"],
            BASE_IDS | {"plan_G0264_img"},
        ),
        ({"img": None, "contents": None}, ["plan_G0264_act"], BASE_IDS),
    ],
)
def test_absent_image_or_points_are_not_referenced(overrides, expected_children, expected_ids):
    envelope = _envelope([_row(**overrides)])

    assert _component(envelope, "plan_G0264")["children"] == expected_children
    # 被省略的可选组件不能残留在组件表里，否则前端会渲染一个空块
    assert {item["id"] for item in _components(envelope)} == expected_ids


def test_row_order_is_preserved():
    envelope = _envelope(
        [
            _row(
                group_code="G0229",
                title="健康",
                title_id=2,
                title_ord_num=2,
                order_num=2053,
            ),
            _row(group_code="G0264", title="寿险", title_id=1, title_ord_num=1),
        ]
    )

    assert _component(envelope, "root")["children"] == ["plan_G0229", "plan_G0264"]


def test_data_model_carries_total_count():
    envelope = _envelope([_row(), _row(group_code="G0208")])

    assert envelope["commands"][2]["updateDataModel"] == {
        "surfaceId": SURFACE_ID,
        "path": "/ui",
        "value": {"total": 2},
    }


def test_empty_rows_produce_no_envelope():
    assert build_plan_card_envelope([], surface_id=SURFACE_ID, catalog_id=CATALOG_ID) is None


def test_component_ids_are_sanitized():
    envelope = _envelope([_row(group_code="G-0264/x")])

    assert _component(envelope, "plan_G_0264_x")["component"] == PLAN_CARD_COMPONENT


def test_format_a2ui_fence_is_parseable_and_prefixed_by_blank_line():
    fence = format_a2ui_fence(_envelope([_row()]))

    assert fence.startswith("\n\n```a2ui\n")
    assert fence.endswith("\n```")
    body = fence.removeprefix("\n\n```a2ui\n").removesuffix("\n```")
    restored = json.loads(body)
    assert restored["surfaceId"] == SURFACE_ID
    assert len(restored["commands"]) == 3


@pytest.fixture
def sqlite_session():
    """只建 plan_shows 一张表的内存库（pgvector 的 document_chunks 在 SQLite 建不出来）。"""
    engine = create_engine("sqlite://")
    PlanShow.metadata.create_all(engine, tables=[PlanShow.__table__])
    with Session(engine) as session:
        yield session


def _add(session, **overrides):
    session.add(_row(**overrides))
    session.commit()


def test_list_plan_shows_sorts_by_category_then_order(sqlite_session):
    _add(sqlite_session, group_code="G0229", title_id=2, title_ord_num=2, order_num=2053)
    _add(sqlite_session, group_code="G0268", title_id=1, title_ord_num=1, order_num=1096)
    _add(sqlite_session, group_code="G0264", title_id=1, title_ord_num=1, order_num=1047)

    rows = list_plan_shows(sqlite_session)

    assert [row.group_code for row in rows] == ["G0264", "G0268", "G0229"]


def test_list_plan_shows_keeps_out_of_sale_rows(sqlite_session):
    """has_sale 的 1/2 语义未确认，因此不过滤，原值随卡片透传给前端。"""
    _add(sqlite_session, group_code="G0298", has_sale="1")
    _add(sqlite_session, group_code="G0264", has_sale="2")

    rows = list_plan_shows(sqlite_session)

    assert sorted(row.has_sale for row in rows) == ["1", "2"]


def test_list_plan_shows_respects_limit(sqlite_session):
    for index in range(3):
        _add(sqlite_session, group_code=f"G{index:04d}", order_num=1000 + index)

    rows = list_plan_shows(sqlite_session, limit=2)

    assert len(rows) == 2
