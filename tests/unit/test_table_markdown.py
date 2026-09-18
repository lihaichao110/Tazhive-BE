"""table_markdown 单元测试：单元格渲染、行列上限与信封合并/降级。"""

import json

from app.services.dataquery.table_markdown import (
    MAX_TABLE_ROWS,
    build_table_markdown,
    merge_table_into_envelope,
)


def test_renders_header_separator_and_rows():
    table = build_table_markdown(["name", "count"], [["甲", 3], ["乙", 2]])
    lines = table.splitlines()
    assert lines[0] == "| name | count |"
    assert lines[1] == "| --- | --- |"
    assert "| 甲 | 3 |" in lines
    assert "| 乙 | 2 |" in lines


def test_cell_rules_for_null_bool_url_and_pipes():
    table = build_table_markdown(
        ["terms_url", "flag", "note"],
        [["https://example.com/a.pdf", True, "含竖线|与换行\n的说明"]],
    )
    assert "[链接](https://example.com/a.pdf)" in table
    assert "| 是 |" in table
    assert "含竖线\\|与换行 的说明" in table


def test_url_parentheses_are_escaped_to_keep_link_intact():
    table = build_table_markdown(["url"], [["https://example.com/(a).pdf"]])
    assert "[链接](https://example.com/%28a%29.pdf)" in table


def test_empty_and_missing_inputs_return_none():
    assert build_table_markdown([], []) is None
    assert build_table_markdown(["a"], []) is None
    assert build_table_markdown([], [["x"]]) is None


def test_row_cap_adds_truncation_note():
    rows = [[f"row-{i}"] for i in range(MAX_TABLE_ROWS + 5)]
    table = build_table_markdown(["col"], rows)
    assert table.count("\n| row-") == MAX_TABLE_ROWS
    assert f"共 {MAX_TABLE_ROWS + 5} 行结果" in table
    assert f"仅展示前 {MAX_TABLE_ROWS} 行" in table


def test_short_rows_padded_to_header_width():
    table = build_table_markdown(["a", "b", "c"], [["x"]])
    assert "| x | - | - |" in table


def test_merge_appends_table_inside_envelope_content():
    envelope = json.dumps(
        {"content": "共 2 款。", "charts": [{"chartId": "c1", "type": "pie"}]},
        ensure_ascii=False,
    )
    merged = merge_table_into_envelope(envelope, "| a |\n| --- |\n| 1 |")
    parsed = json.loads(merged)
    assert parsed["content"] == "共 2 款。\n\n| a |\n| --- |\n| 1 |"
    assert parsed["charts"] == [{"chartId": "c1", "type": "pie"}]


def test_merge_falls_back_to_plain_concat_when_envelope_invalid():
    assert merge_table_into_envelope("不是 JSON", "| a |") == "不是 JSON\n\n| a |"
    array_body = json.dumps(["a"])
    assert merge_table_into_envelope(array_body, "| a |") == '["a"]\n\n| a |'
    content_not_str = json.dumps({"content": 1})
    assert merge_table_into_envelope(content_not_str, "| a |") == '{"content": 1}\n\n| a |'
