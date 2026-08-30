from pydantic import BaseModel
from datetime import datetime


class ThreadCreate(BaseModel):
    """会话创建请求模型
    用于接收创建会话时前端传入的参数
    """
    # 会话标题，允许为空，非必填
    title: str | None = None


class ThreadRead(BaseModel):
    """会话读取返回模型
    用于接口查询会话信息，返回给前端的数据结构
    """
    # 会话唯一ID
    id: str
    # 创建该会话的用户ID
    user_id: str
    # 会话标题，可以为None
    title: str | None
    # 会话状态，例如正常、归档、删除等状态标识
    status: str
    # 会话创建时间
    created_at: datetime
    # 会话最后更新时间
    updated_at: datetime
