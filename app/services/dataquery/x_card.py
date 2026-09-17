"""查询结果表格的 A2UI v0.9（@ant-design/x-card）信封构造。

与 plans/x_card.py 同构：createSurface / updateComponents / updateDataModel
三段命令 + 扁平邻接表。组件契约见 docs/a2ui-data-table.md；前端未注册
DataTable 组件时会把未知组件渲染成占位文本，但回答正文仍含完整文字总结，
不影响可用性。
"""

from typing import Any

from app.services.plans.x_card import A2UI_VERSION, ROOT_COMPONENT_ID

DATA_TABLE_COMPONENT = "DataTable"

MAX_CARD_ROWS = 20
"""卡片最多渲染的行数，超出部分以回答正文为准。"""

MAX_CARD_COLUMNS = 8
"""卡片最多渲染的列数（从左往右保留），超宽表格交给前端横向滚动或正文总结。"""


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def build_table_envelope(
    columns: list[str],
    rows: list[list[Any]],
    *,
    surface_id: str,
    catalog_id: str,
) -> dict[str, Any] | None:
    """生成 {"surfaceId","commands"} 信封；无列或无行时返回 None 不出卡。"""
    if not columns or not rows:
        return None
    truncated = len(rows) > MAX_CARD_ROWS
    card_columns = [str(column) for column in columns[:MAX_CARD_COLUMNS]]
    card_rows = [[_cell(cell) for cell in row[:MAX_CARD_COLUMNS]] for row in rows[:MAX_CARD_ROWS]]
    components: list[dict[str, Any]] = [
        {
            "id": ROOT_COMPONENT_ID,
            "component": DATA_TABLE_COMPONENT,
            "columns": card_columns,
            "rows": card_rows,
            "truncated": truncated,
        }
    ]
    commands: list[dict[str, Any]] = [
        {
            "version": A2UI_VERSION,
            "createSurface": {"surfaceId": surface_id, "catalogId": catalog_id},
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        },
        {
            "version": A2UI_VERSION,
            "updateDataModel": {
                "surfaceId": surface_id,
                "path": "/ui",
                "value": {"total": len(rows), "truncated": truncated},
            },
        },
    ]
    return {"surfaceId": surface_id, "commands": commands}


__all__ = ["DATA_TABLE_COMPONENT", "MAX_CARD_ROWS", "build_table_envelope"]
