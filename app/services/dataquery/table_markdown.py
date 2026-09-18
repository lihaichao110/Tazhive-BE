"""查询结果表格的 Markdown 渲染与图表信封合并。

data_query 意图下前端要求 assistant 消息是单一合法 JSON 信封
（{"content":…,"charts":…}，契约见 docs/a2ui-data-table.md），表格因此
不能以 a2ui 围栏追加在信封之外；由服务端在流结束后把表格 Markdown
并入信封 content 字段并整体重新序列化，保证流式下发与落库内容同形。
"""

import json
from typing import Any

from app.core.logging import logger

MAX_TABLE_ROWS = 20
"""表格最多渲染的行数，超出部分以截断提示与回答正文总结为准。"""

MAX_TABLE_COLUMNS = 8
"""表格最多渲染的列数（从左往右保留），超宽表格交给前端横向滚动或正文总结。"""


def _cell_text(value: Any) -> str:
    """单元格转 Markdown 安全文本；空值显示 -，URL 渲染为可点击链接。"""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    text = str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return "-"
    if text.startswith(("http://", "https://")):
        # 圆括号会截断 Markdown 链接语法，做百分号转义保住 URL 完整性
        safe_url = text.replace("(", "%28").replace(")", "%29")
        return f"[链接]({safe_url})"
    return text


def build_table_markdown(columns: list[str], rows: list[list[Any]]) -> str | None:
    """把查询结果渲染为 Markdown 表格；无行或无列时返回 None 不出表格。"""
    if not columns or not rows:
        return None
    headers = [str(column).replace("|", "\\|") for column in columns[:MAX_TABLE_COLUMNS]]
    lines = [
        f"| {' | '.join(headers)} |",
        f"|{' --- |' * len(headers)}",
    ]
    for row in rows[:MAX_TABLE_ROWS]:
        cells = [_cell_text(cell) for cell in row[:MAX_TABLE_COLUMNS]]
        # 行数据比表头短时补占位符，保证 Markdown 列数与表头一致
        cells += ["-"] * (len(headers) - len(cells))
        lines.append(f"| {' | '.join(cells)} |")
    if len(rows) > MAX_TABLE_ROWS:
        lines.append("")
        lines.append(f"> 共 {len(rows)} 行结果，表格仅展示前 {MAX_TABLE_ROWS} 行。")
    return "\n".join(lines)


def merge_table_into_envelope(content: str, table_markdown: str) -> str:
    """把表格 Markdown 并入图表信封的 content 字段并整体重新序列化。

    模型输出不是合法信封 JSON（或 content 字段不是字符串）时无法安全改写，
    退化为「原文 + 表格」拼接：前端按纯文本降级展示，表格内容仍然可见。
    """
    fallback = f"{content.rstrip()}\n\n{table_markdown}"
    try:
        envelope = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("data_query 回复不是合法 JSON 信封，表格按纯文本拼接降级")
        return fallback
    if not isinstance(envelope, dict) or not isinstance(envelope.get("content"), str):
        logger.warning("data_query 回复缺少字符串 content 字段，表格按纯文本拼接降级")
        return fallback
    envelope["content"] = envelope["content"].rstrip() + "\n\n" + table_markdown
    return json.dumps(envelope, ensure_ascii=False)
