from typing import Any

from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, AIMessageChunk

from app.schemas.reference import Reference, dump_references
from app.services.rag.retriever import RetrievedChunk

REFERENCE_METADATA_KEY = "references"
MAX_REFERENCE_SNIPPET_CHARS = 500
REFERENCE_STREAM_EVENT = "references"


def _snippet(value: Any) -> str:
    return str(value or "").strip()[:MAX_REFERENCE_SNIPPET_CHARS]


def build_rag_references(chunks: list[RetrievedChunk]) -> list[dict]:
    """按文档与片段去重，生成与实际注入模型一致的 RAG 来源。"""

    references: list[Reference] = []
    seen: set[tuple[str, int]] = set()
    for chunk in chunks:
        if not isinstance(chunk.document_id, str) or not isinstance(chunk.chunk_index, int):
            continue
        key = (chunk.document_id, chunk.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        source = (chunk.meta_data or {}).get("source")
        title = str(source or f"文档 {chunk.document_id}").strip()
        references.append(
            Reference(
                source_type="rag",
                title=title,
                url=f"/api/v1/documents/{chunk.document_id}/chunks/{chunk.chunk_index}",
                snippet=_snippet(chunk.content),
                document_id=chunk.document_id,
                chunk_index=chunk.chunk_index,
            )
        )
    return dump_references(references)


def build_web_references(results: list[dict[str, str]]) -> list[dict]:
    """将已规范化、去重后的联网搜索结果转换为统一来源。"""

    return dump_references(
        [
            Reference(
                source_type="web",
                title=result["title"],
                url=result["url"],
                snippet=_snippet(result.get("content")),
            )
            for result in results
        ]
    )


def attach_references(response: ModelResponse, references: list[dict]) -> ModelResponse:
    """把确定性来源附加到本次模型调用产生的 AI 消息。"""

    for message in response.result:
        if isinstance(message, (AIMessage, AIMessageChunk)):
            message.additional_kwargs[REFERENCE_METADATA_KEY] = references
    return response


def extract_message_references(message: AIMessage | AIMessageChunk | None) -> list[dict]:
    """从 AI 消息扩展字段读取来源，异常形状安全降级为空数组。"""

    if message is None:
        return []
    raw = message.additional_kwargs.get(REFERENCE_METADATA_KEY)
    if not isinstance(raw, list):
        return []
    references: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            references.append(Reference.model_validate(item).model_dump(mode="json"))
        except ValueError:
            continue
    return references


def make_reference_stream_event(references: list[dict]) -> dict:
    """构造仅供聊天出口消费、不会直接透传给前端的内部流事件。"""

    return {"type": REFERENCE_STREAM_EVENT, "references": references}
