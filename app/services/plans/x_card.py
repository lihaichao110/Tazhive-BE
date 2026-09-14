"""把 plan_shows 的行数据构造成 A2UI v0.9（@ant-design/x-card）命令。

前端按「```a2ui 围栏」解析助手正文里的 {"surfaceId","commands"} 信封，
所以本模块只负责命令构造与围栏格式化，不涉及 SSE 帧结构。
组件契约见 docs/a2ui-plan-cards.md 与 docs/catalogs/plan_show_catalog.json。
"""

import json
import re
from typing import Any

from app.models.plan_show import PlanShow

A2UI_VERSION = "v0.9"
A2UI_FENCE_LANGUAGE = "a2ui"

ROOT_COMPONENT_ID = "root"
PLAN_LIST_COMPONENT = "PlanList"
PLAN_CARD_COMPONENT = "PlanCard"
PLAN_IMAGE_COMPONENT = "PlanImage"
PLAN_POINTS_COMPONENT = "PlanPoints"
PLAN_ACTIONS_COMPONENT = "PlanActions"
PLAN_BUTTON_COMPONENT = "PlanActionButton"

PRE_UNDERWRITE_BUTTON_TEXT = "预核保"
PRE_UNDERWRITE_BUTTON_COLOR = "#699bf6"
PRE_UNDERWRITE_ACTION_NAME = "plan_pre_underwrite"
APPLY_BUTTON_TEXT = "正式投保"
APPLY_BUTTON_COLOR = "#028550"
APPLY_ACTION_NAME = "plan_apply"
BUTTON_TEXT_COLOR = "#ffffff"
BUTTON_BORDER_RADIUS = "6px"

# groupCode 是业务自然主键（如 G0264），清洗掉不适合做组件 id 的字符
_UNSAFE_ID_CHARS = re.compile(r"[^0-9A-Za-z_]+")


def _component_id(group_code: str, suffix: str = "") -> str:
    """方案内组件 id：`plan_G0264` / `plan_G0264_img`。"""
    safe = _UNSAFE_ID_CHARS.sub("_", group_code).strip("_") or "plan"
    return f"plan_{safe}_{suffix}" if suffix else f"plan_{safe}"


def _split_points(contents: str | None) -> list[str]:
    """卖点文案源数据以 CRLF 分隔（可能混用 LF），拆成非空条目列表。"""
    if not contents:
        return []
    return [line.strip() for line in contents.splitlines() if line.strip()]


def _action_context(row: PlanShow) -> dict[str, Any]:
    """按钮回传的方案标识：字面量而非 {path}，点击时由 X-Card 原样透传给 onAction。

    insur_list 是投保/预核保所需的险种代码（如 ["AYR","AYS","AYT"]）。
    """
    return {
        "group_code": row.group_code,
        "group_name": row.group_name,
        "title": row.title,
        "insur_list": list(row.insur_list or []),
    }


def _action_button(
    *,
    component_id: str,
    text: str,
    background_color: str,
    action_name: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": component_id,
        "component": PLAN_BUTTON_COMPONENT,
        "text": text,
        "backgroundColor": background_color,
        "color": BUTTON_TEXT_COLOR,
        "borderRadius": BUTTON_BORDER_RADIUS,
        "action": {"event": {"name": action_name, "context": context}},
    }


def build_plan_card_envelope(
    rows: list[PlanShow], *, surface_id: str, catalog_id: str
) -> dict[str, Any] | None:
    """生成 {"surfaceId","commands"} 信封；没有方案时返回 None，由调用方决定不出卡。

    保持传入行的顺序（调用方按 title_ord_num/order_num 排好序），组件用扁平
    邻接表（A2UI 规范要求），每张卡的字面量 props 直接携带业务数据。
    """
    if not rows:
        return None

    components: list[dict[str, Any]] = []
    card_ids: list[str] = []

    for row in rows:
        card_id = _component_id(row.group_code)
        image_id = _component_id(row.group_code, "img")
        points_id = _component_id(row.group_code, "points")
        actions_id = _component_id(row.group_code, "act")
        children: list[str] = []

        # 配图与卖点都可能缺失（源数据 imageURL / contents 可空），缺失时不引用对应组件
        image = None
        if row.img:
            image = {
                "id": image_id,
                "component": PLAN_IMAGE_COMPONENT,
                "url": row.img,
                "altText": row.group_name,
            }
            children.append(image_id)

        points = _split_points(row.contents)
        points_component = None
        if points:
            points_component = {
                "id": points_id,
                "component": PLAN_POINTS_COMPONENT,
                "items": points,
            }
            children.append(points_id)

        context = _action_context(row)
        actions_children = [
            _component_id(row.group_code, "pre"),
            _component_id(row.group_code, "apply"),
        ]
        children.append(actions_id)

        card_ids.append(card_id)
        components.append(
            {
                "id": card_id,
                "component": PLAN_CARD_COMPONENT,
                "groupCode": row.group_code,
                "groupName": row.group_name,
                "title": row.title,
                "hasSale": row.has_sale,
                "children": children,
            }
        )
        if image is not None:
            components.append(image)
        if points_component is not None:
            components.append(points_component)
        components.append(
            {
                "id": actions_id,
                "component": PLAN_ACTIONS_COMPONENT,
                "children": actions_children,
            }
        )
        components.append(
            _action_button(
                component_id=actions_children[0],
                text=PRE_UNDERWRITE_BUTTON_TEXT,
                background_color=PRE_UNDERWRITE_BUTTON_COLOR,
                action_name=PRE_UNDERWRITE_ACTION_NAME,
                context=context,
            )
        )
        components.append(
            _action_button(
                component_id=actions_children[1],
                text=APPLY_BUTTON_TEXT,
                background_color=APPLY_BUTTON_COLOR,
                action_name=APPLY_ACTION_NAME,
                context=context,
            )
        )

    commands: list[dict[str, Any]] = [
        {
            "version": A2UI_VERSION,
            "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {
                "surfaceId": surface_id,
                "components": [
                    {
                        "id": ROOT_COMPONENT_ID,
                        "component": PLAN_LIST_COMPONENT,
                        "children": card_ids,
                    },
                    *components,
                ],
            },
        },
        {
            "version": A2UI_VERSION,
            "updateDataModel": {
                "surfaceId": surface_id,
                "path": "/ui",
                "value": {"total": len(card_ids)},
            },
        },
    ]
    return {"surfaceId": surface_id, "commands": commands}


def format_a2ui_fence(envelope: dict[str, Any]) -> str:
    """按前端解析约定，把信封渲染成正文里的 ```a2ui 围栏块。"""
    payload = json.dumps(envelope, ensure_ascii=False)
    return f"\n\n```{A2UI_FENCE_LANGUAGE}\n{payload}\n```"
