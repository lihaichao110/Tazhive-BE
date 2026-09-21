from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".txt", ".markdown"}


def parse_text_file(path: Path) -> str:
    """读取纯文本类文件，返回原始文本。"""
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的文件类型: {path.suffix}")
    return path.read_text(encoding="utf-8", errors="replace")
