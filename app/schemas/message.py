from pydantic import BaseModel
from datetime import datetime


class MessageCreate(BaseModel):
    """消息创建请求模型
    接收前端发送消息时传入的请求体参数
    """
    # 消息文本内容
    content: str
    # 消息角色：user 用户消息 / assistant AI回复消息，默认为用户消息
    role: str = "user"  # 默认用户消息


class MessageRead(BaseModel):
    """消息读取返回模型
    查询消息后返回给前端的数据结构
    """
    # 消息唯一ID
    id: str
    # 所属会话ID，关联thread
    thread_id: str
    # 消息角色 user / assistant
    role: str
    # 消息文本内容
    content: str
    # 消息创建时间
    created_at: datetime
