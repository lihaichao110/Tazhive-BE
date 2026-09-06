from dataclasses import dataclass
from sqlalchemy import text
from sqlmodel import Session
from app.services.database import engine
from app.core.logging import logger


@dataclass
class RetrievedChunk:
    """向量检索结果载体：携带分块内容与相似度评分，避免给 ORM 模型附加临时属性。"""
    content: str
    similarity: float = 0.0
    overlap_score: int = 0
    document_id: str | None = None
    chunk_index: int | None = None


def retrieve_similar_chunks(query_embedding: list[float], top_k: int = 5, session: Session | None = None) -> list[RetrievedChunk]:
    """
    使用 pgvector 的余弦相似度检索最相关的文档分块。
    参数：
        query_embedding: 查询向量
        top_k: 返回数量
        session: 可选的 SQLModel Session（若未提供，则创建新的）
    返回：
        RetrievedChunk 对象列表（按相似度降序）
    """
    own_session = False
    if session is None:
        session = Session(engine)
        own_session = True

    try:
        # 将向量列表转换为 PostgreSQL vector 可接受的字符串格式
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # 使用原生 SQL 执行向量检索（pgvector 支持 <=> 表示余弦距离）
        sql = text("""
            SELECT id, document_id, chunk_index, content, meta_data,
                   1 - (embedding <=> (:embedding)::vector) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> (:embedding)::vector
            LIMIT :top_k
        """)
        result = session.exec(
            sql,
            params={"embedding": embedding_str, "top_k": top_k}
        ).all()

        logger.info(f'向量库结果：{result}')

        # 构造 RetrievedChunk（轻量载体，不重新加载 embedding，避免大对象）
        chunks = [
            RetrievedChunk(
                content=row.content,
                similarity=float(row.similarity),
                document_id=row.document_id,
                chunk_index=row.chunk_index,
            )
            for row in result
        ]
        return chunks
    finally:
        if own_session:
            session.close()