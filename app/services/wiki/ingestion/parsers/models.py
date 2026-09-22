from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class SourceBatch:
    """一段可以安全提交给 LLM 的源内容。"""

    section_name: str
    part_number: int
    text: str
    row_start: int | None = None
    row_end: int | None = None
    detail_markdown: str | None = None


@dataclass(frozen=True)
class ParsedSource:
    """所有源文件解析器统一返回的结构。"""

    kind: Literal["text", "table"]
    batches: tuple[SourceBatch, ...]

