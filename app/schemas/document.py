from pydantic import BaseModel
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    """文档上传接口返回实体"""
    document_id: str
    """文档唯一标识ID"""
    filename: str
    """上传文件原始名称"""
    status: str
    """文档处理状态"""
    chunk_count: int
    """文档拆分后的分片数量"""


class DocumentRead(BaseModel):
    """文档详情查询返回实体"""
    id: str
    """文档唯一主键ID"""
    filename: str
    """文件原始名称"""
    file_type: str
    """文件后缀类型，如 pdf / docx / md / txt / xlsx"""
    status: str
    """文档解析处理状态"""
    chunk_count: int
    """文本分块总数"""
    created_at: datetime
    """文档上传创建时间"""
