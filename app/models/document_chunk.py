from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Integer, String, Text
from sqlmodel import Column, Field

from app.models.base import BaseModel


class DocumentChunk(BaseModel, table=True):
    __tablename__ = "document_chunks"

    document_id: str = Field(
        sa_column=Column(String(64), index=True, nullable=False, comment="文档唯一标识ID")
    )
    chunk_index: int = Field(
        sa_column=Column(
            "chunk_index", Integer, nullable=False, comment="分片序号，标记当前文档内第几个切片"
        )
    )
    content: str = Field(sa_column=Column(Text, nullable=False, comment="文本分片原始内容"))
    # 嵌入向量，维度取决于 embedding 模型（OpenAI text‑embedding‑3‑small 为 1536）
    embedding: list[float] = Field(
        sa_column=Column(Vector(1024), nullable=True, comment="文本向量Embedding，1024维浮点数数组")
    )
    meta_data: dict | None = Field(
        default=None, sa_column=Column(JSON, comment="自定义扩展元数据，存储附加业务信息")
    )
