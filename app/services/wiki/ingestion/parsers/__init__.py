from pathlib import Path

from app.services.wiki.ingestion.parsers.models import ParsedSource, SourceBatch
from app.services.wiki.ingestion.parsers.spreadsheet import (
    SUPPORTED_SUFFIXES as SPREADSHEET_SUFFIXES,
)
from app.services.wiki.ingestion.parsers.spreadsheet import parse_spreadsheet
from app.services.wiki.ingestion.parsers.text import parse_text_file


def parse_source(path: Path, *, batch_chars: int = 24_000) -> ParsedSource:
    """根据文件类型分发到具体解析器。"""
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt", ".markdown"}:
        return ParsedSource(
            kind="text",
            batches=(
                SourceBatch(
                    section_name=path.stem,
                    part_number=1,
                    text=parse_text_file(path),
                ),
            ),
        )
    if suffix in SPREADSHEET_SUFFIXES:
        return parse_spreadsheet(path, batch_chars=batch_chars)

    raise ValueError(f"不存在: {suffix} 后缀注册解析器")
