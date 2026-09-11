from datetime import date, datetime, time
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


class DocumentParseError(ValueError):
    """表示上传文件本身无法解析，调用方应将其视为客户端输入错误。"""


def _format_excel_cell(value: object) -> str:
    """将 Excel 单元格转换为稳定的单行文本，避免破坏表格行列结构。"""
    if value is None:
        return ""
    if isinstance(value, (datetime, date, time)):
        text = value.isoformat()
    else:
        text = str(value)
    return (
        text.replace("\t", " ")
        .replace("\r\n", " ")
        .replace("\r", " ")
        .replace("\n", " ")
        .strip()
    )


def _load_excel(path: Path) -> list[str]:
    """加载所有可见且包含有效内容的工作表，并转换为制表符分隔文本。"""
    workbook = None
    try:
        # data_only=False 保留公式表达式；keep_links=False 避免加载外部工作簿链接。
        workbook = load_workbook(
            filename=path,
            read_only=True,
            data_only=False,
            keep_links=False,
        )
        texts: list[str] = []
        for worksheet in workbook.worksheets:
            if worksheet.sheet_state != "visible":
                continue

            rows: list[str] = []
            for row in worksheet.iter_rows(values_only=True):
                cells = [_format_excel_cell(value) for value in row]
                # 清除尾部空单元格，同时保留行首空单元格以维持列位置。
                while cells and not cells[-1]:
                    cells.pop()
                if cells and any(cells):
                    rows.append("\t".join(cells))

            if rows:
                sheet_name = _format_excel_cell(worksheet.title)
                texts.append(f"工作表: {sheet_name}\n" + "\n".join(rows))

        if not texts:
            raise DocumentParseError("Excel 文件中没有可提取的有效内容")
        return texts
    except DocumentParseError:
        raise
    except (
        BadZipFile,
        InvalidFileException,
        ParseError,
        EOFError,
        KeyError,
        OSError,
        ValueError,
    ) as exc:
        raise DocumentParseError("Excel 文件损坏、已加密或格式无效") from exc
    finally:
        if workbook is not None:
            workbook.close()

def load_document(file_path: str) -> list[str]:
    """加载文档并返回纯文本列表（按页或整个）"""
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext in [".txt", ".md"]:
        loader = TextLoader(str(path), encoding="utf-8")
        docs = loader.load()
        return [doc.page_content for doc in docs]
    elif ext == ".pdf":
        loader = PyPDFLoader(str(path))
        docs = loader.load()
        return [doc.page_content for doc in docs]
    elif ext == ".docx":
        loader = Docx2txtLoader(str(path))
        docs = loader.load()
        return [doc.page_content for doc in docs]
    elif ext == ".xlsx":
        return _load_excel(path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")
