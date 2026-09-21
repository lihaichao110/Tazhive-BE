from pathlib import Path

from app.services.wiki.ingestion.parsers.text import parse_text_file


def parse_source(path: Path) -> str:
    """根据文件类型分发到具体解析器。"""
    suffix = path.suffix.lower()

    if suffix in {".md", ".txt", ".markdown"}:
        return parse_text_file(path)

    raise ValueError(f"不存在: {suffix} 后缀注册解析器")
