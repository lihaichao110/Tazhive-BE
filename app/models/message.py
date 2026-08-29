from sqlmodel import Field, Column, String, Integer, Text
from app.models.base import BaseModel


class Message(BaseModel, table=True):
    """对话消息表，存储会话下每一条聊天记录，一条Thread对应多条Message"""
    __tablename__ = "messages"

    # 所属会话ID，关联threads表id
    thread_id: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="所属会话ID，关联threads表主键id"
        )
    )

    # 消息角色，限制长度，仅允许 user / assistant / system / tool
    role: str = Field(
        sa_column=Column(
            String(50),
            nullable=False,
            comment="消息角色: user / assistant / system / tool"
        )
    )

    # 消息正文：允许为NULL，模型只调用工具无文本输出时content为null
    content: str | None = Field(
        sa_column=Column(
            Text,
            nullable=True,
            comment="消息文本内容；工具调用消息可存null"
        )
    )

    # 本条消息token消耗数量，用于统计计费
    token_count: int | None = Field(
        sa_column=Column(
            Integer,
            default=None,
            nullable=True,
            comment="本条消息token消耗数量，用于统计计费，可为null"
        )
    )

    # 扩展元数据，PG JSONB，存放tool_calls、trace等
    meta_data: str | None = Field(
        sa_column=Column(
            Text,
            default=None,
            nullable=True,
            comment="扩展元数据，保存JSON字符串；工具调用、trace附加信息，业务自行序列化解析"
        )
    )
