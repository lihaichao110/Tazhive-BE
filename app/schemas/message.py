from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.reference import Reference


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
    # 回答引用来源；用户消息和无来源回答为空数组
    references: list[Reference] = Field(default_factory=list)
    # 消息创建时间
    created_at: datetime
    # 使用量元数据（token消耗等信息）
    usage_metadata: dict[str, Any] | None = None
    # 模型响应元数据
    response_metadata: dict[str, Any] | None = None
    # 附加扩展字段
    additional_kwargs: dict[str, Any] | None = None
    # 工具调用列表
    tool_calls: list[Any] | None = None
    # 无效工具调用列表
    invalid_tool_calls: list[Any] | None = None
    # 底层原始消息标识ID
    message_id: str | None = None
