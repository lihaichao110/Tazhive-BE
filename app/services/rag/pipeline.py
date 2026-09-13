from pathlib import Path

from sqlmodel import Session

from app.core.logging import logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.rag.chunker import chunk_text
from app.services.rag.embedder import get_embedder
from app.services.rag.loader import load_document


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
        all_chunks = []
        for text in texts:
            all_chunks.extend(chunk_text(text))

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
