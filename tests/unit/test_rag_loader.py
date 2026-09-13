from datetime import date, datetime

import pytest
from openpyxl import Workbook

from app.services.rag.chunker import chunk_text
from app.services.rag.loader import DocumentParseError, load_document


def test_load_xlsx_extracts_visible_sheets_and_normalizes_values(tmp_path):
    workbook = Workbook()
    first_sheet = workbook.active
    first_sheet.title = "汇总"
    first_sheet.append(["名称", "数量", "日期", "更新时间", "计算值"])
    first_sheet.append(["A\n产品", 12, date(2026, 9, 11), datetime(2026, 9, 11, 8, 30), "=B2*2"])
    first_sheet.append([None, None, None, None, None])

    second_sheet = workbook.create_sheet("明细")
    second_sheet.append([None, "保留列位置", "包含\t制表符"])

    hidden_sheet = workbook.create_sheet("内部数据")
    hidden_sheet.append(["不应被提取"])
    hidden_sheet.sheet_state = "hidden"

    file_path = tmp_path / "sample.xlsx"
    workbook.save(file_path)
    workbook.close()

    texts = load_document(str(file_path))

    assert len(texts) == 2
    assert texts[0].startswith("工作表: 汇总\n")
    assert "A 产品\t12\t2026-09-11T00:00:00\t2026-09-11T08:30:00\t=B2*2" in texts[0]
    assert texts[1] == "工作表: 明细\n\t保留列位置\t包含 制表符"
    assert all("内部数据" not in text for text in texts)
    assert all("不应被提取" not in text for text in texts)

    # Excel 提取结果应能直接复用现有 RAG 分块逻辑。
    chunks = [chunk for text in texts for chunk in chunk_text(text)]
    assert chunks
    assert all(chunk.strip() for chunk in chunks)


def test_load_xlsx_rejects_workbook_without_visible_content(tmp_path):
    workbook = Workbook()
    workbook.active.title = "空白页"
    hidden_sheet = workbook.create_sheet("隐藏内容")
    hidden_sheet.append(["不参与解析"])
    hidden_sheet.sheet_state = "hidden"

    file_path = tmp_path / "empty.xlsx"
    workbook.save(file_path)
    workbook.close()

    with pytest.raises(DocumentParseError, match="没有可提取的有效内容"):
        load_document(str(file_path))


def test_load_xlsx_rejects_invalid_file(tmp_path):
    file_path = tmp_path / "broken.xlsx"
    file_path.write_bytes(b"not an excel workbook")

    with pytest.raises(DocumentParseError, match="损坏、已加密或格式无效"):
        load_document(str(file_path))
