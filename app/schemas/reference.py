from typing import Literal

from pydantic import BaseModel


class Reference(BaseModel):
    """提供给前端展示的统一回答来源。"""

    source_type: Literal["rag", "web"]
    title: str
    url: str
    snippet: str
    document_id: str | None = None
    chunk_index: int | None = None


def dump_references(references: list[Reference]) -> list[dict]:
    """转换为可直接写入 JSON 列与 SSE 的普通字典。"""

    return [reference.model_dump(mode="json") for reference in references]
