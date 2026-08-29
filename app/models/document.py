from sqlalchemy import Integer
from sqlmodel import Field, Column, String
from app.models.base import BaseModel


class Document(BaseModel, table=True):
    """文档上传记录表，保存RAG上传的原始文件信息，记录文件解析、分片状态"""
    __tablename__ = "documents"

    # 原始上传文件名，建立索引便于按文件名检索
    filename: str = Field(
        sa_column=Column(
            String(512),
            index=True,
            nullable=False,
            comment="上传的原始文件名称"
        )
    )

    # 文件类型，限定pdf / docx / md / txt
    file_type: str = Field(
        sa_column=Column(
            String(50),
            nullable=False,
            comment="文件类型：pdf / docx / md / txt"
        )
    )

    # 文件内容哈希值，用于重复文件去重校验
    content_hash: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="文件内容hash摘要，用于重复文件去重"
        )
    )

    # 文档解析之后拆分出来的分片数量，默认0，解析完成后更新
    chunk_count: int = Field(
        sa_column=Column(
            Integer,
            default=0,
            nullable=False,
            comment="文档解析后生成的文本分片数量，解析完成回填"
        )
    )

    # 文档处理状态：pending待处理 / processing解析中 / done解析完成 / error处理失败
    status: str = Field(
        sa_column=Column(
            String(50),
            default="pending",
            nullable=False,
            comment="文档处理状态：pending待处理、processing解析中、done解析完成、error处理失败"
        )
    )