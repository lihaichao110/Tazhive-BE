from pathlib import Path

from sqlmodel import Session

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


def ingest_document(file_path: str, filename: str, db: Session) -> str:
    """处理文档：加载、分块、嵌入、存储，返回 document_id"""
    # 创建 Document 记录
    doc = Document(
        filename=filename,
        file_type=Path(file_path).suffix.lower().lstrip("."),
        content_hash="",  # 可后续计算哈希去重
        status="processing",
        chunk_count=0,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_id = doc.id

    try:
        texts = load_document(file_path)
        all_chunks = build_chunks(texts, doc.file_type)

        embedder = get_embedder()
        embeddings = embedder.embed_documents(all_chunks)

        # 先完整校验数量，再写入 Session，避免不一致时遗留部分待提交的分块。
        chunk_embeddings = list(zip(all_chunks, embeddings, strict=True))
        for idx, (chunk_text_content, embedding) in enumerate(chunk_embeddings):
            chunk = DocumentChunk(
                document_id=doc_id,
                chunk_index=idx,
                content=chunk_text_content,
                embedding=embedding,
                meta_data={"source": filename},
            )
            db.add(chunk)

        doc.status = "done"
        doc.chunk_count = len(all_chunks)
        db.commit()
        logger.info(f"文档 {doc_id} 对应的 {len(all_chunks)} chunks")
        return doc_id
    except Exception as e:
        doc.status = "error"
        db.commit()
        logger.error(f"写入失败 {doc_id}: {e}")
        raise
