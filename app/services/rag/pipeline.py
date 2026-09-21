import hashlib
from pathlib import Path
from typing import Any

from sqlmodel import Session, col, delete, select

from app.core.logging import logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.rag.chunker import chunk_text
from app.services.rag.embedder import get_embedder
from app.services.rag.loader import load_document

# Excel 行记录的自包含长度上限：不超过该长度时直接作为 chunk，避免通用切片
# 在记录内部的句读处再次截断；超长记录回退通用切片。
_XLSX_ROW_CHUNK_LIMIT = 1000


def build_chunks(texts: list[str], file_type: str) -> list[str]:
    """按文件类型把加载文本转换为 chunk 列表。

    xlsx 的加载结果已是行级自包含记录，直接作为 chunk；其余类型沿用通用切片。
    """
    chunks: list[str] = []
    if file_type == "xlsx":
        for record in texts:
            if len(record) <= _XLSX_ROW_CHUNK_LIMIT:
                chunks.append(record)
            else:
                chunks.extend(chunk_text(record))
        return chunks
    for text in texts:
        chunks.extend(chunk_text(text))
    return chunks


def ingest_document(
    file_path: str,
    filename: str,
    db: Session,
    *,
    metadata: dict[str, Any] | None = None,
    document_key: str | None = None,
) -> str:
    """处理文档：加载、分块、嵌入、存储，返回 document_id"""
    content_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
    doc = None
    if document_key is not None:
        doc = db.exec(select(Document).where(Document.filename == document_key)).first()
        if doc is not None and doc.content_hash == content_hash and doc.status == "done":
            logger.info("文档内容未变化，跳过重复摄入：%s", document_key)
            return doc.id

    # document_key 用作可重复定位的内部来源键；普通上传仍显示原文件名。
    if doc is None:
        doc = Document(
            filename=document_key or filename,
            file_type=Path(file_path).suffix.lower().lstrip("."),
            content_hash=content_hash,
            status="processing",
            chunk_count=0,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
    else:
        doc.status = "processing"
        doc.content_hash = content_hash

    doc_id = doc.id

    try:
        texts = load_document(file_path)
        all_chunks = build_chunks(texts, doc.file_type)

        embedder = get_embedder()
        embeddings = embedder.embed_documents(all_chunks)

        # 先完整校验数量，再写入 Session，避免不一致时遗留部分待提交的分块。
        chunk_embeddings = list(zip(all_chunks, embeddings, strict=True))
        if document_key is not None:
            db.exec(delete(DocumentChunk).where(col(DocumentChunk.document_id) == doc_id))
        chunk_metadata = {"source": filename, **(metadata or {})}
        for idx, (chunk_text_content, embedding) in enumerate(chunk_embeddings):
            chunk = DocumentChunk(
                document_id=doc_id,
                chunk_index=idx,
                content=chunk_text_content,
                embedding=embedding,
                meta_data=chunk_metadata.copy(),
            )
            db.add(chunk)

        doc.status = "done"
        doc.chunk_count = len(all_chunks)
        db.commit()
        logger.info(f"文档 {doc_id} 对应的 {len(all_chunks)} chunks")
        return doc_id
    except Exception as e:
        # 避免异常发生在写入中途时把部分 chunk 一并提交。
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        get = getattr(db, "get", None)
        persisted_doc = get(Document, doc_id) if callable(get) else doc
        if persisted_doc is None:
            persisted_doc = doc
            db.add(persisted_doc)
        persisted_doc.status = "error"
        db.commit()
        logger.error(f"写入失败 {doc_id}: {e}")
        raise
