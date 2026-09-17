from datetime import timedelta

from sqlmodel import JSON, Column, Field, String, Text

from app.models.base import BaseModel


class Message(BaseModel, table=True):
    """对话消息表，存储会话下每一条聊天记录，一条Thread对应多条Message"""

    __tablename__ = "messages"

    # 所属会话ID，关联threads表id
    thread_id: str = Field(
        sa_column=Column(
            String(64), index=True, nullable=False, comment="所属会话ID，关联threads表主键id"
        )
    )

    # 消息角色，限制长度，仅允许 user / assistant / system / tool
    role: str = Field(
        sa_column=Column(
            String(50), nullable=False, comment="消息角色: user / assistant / system / tool"
        )
    )

    # 消息正文，对应LangChain Message.content字段
    content: str | None = Field(
        sa_column=Column(Text, nullable=True, comment="消息文本内容；仅工具调用无输出时可为null")
    )

    # LangChain usage_metadata，输入输出、缓存读写token统计
    usage_metadata: dict | None = Field(
        sa_column=Column(
            JSON,
            nullable=True,
            default=None,
            comment="langchain usage_metadata，输入输出、缓存读写token统计信息",
        )
    )

    # LangChain AIMessage.response_metadata，模型响应完整元信息
    response_metadata: dict | None = Field(
        sa_column=Column(
            JSON,
            nullable=True,
            default=None,
            comment="AIMessage.response_metadata，模型返回完整响应元数据",
        )
    )

    # 模型扩展返回字段，厂商自定义额外字段
    additional_kwargs: dict | None = Field(
        sa_column=Column(
            JSON,
            nullable=True,
            default=None,
            comment="additional_kwargs，厂商扩展字段：reasoning_content、refusal、搜索信息等",
        )
    )

    # 工具调用请求数组，AIMessage.tool_calls
    tool_calls: list | None = Field(
        sa_column=Column(
            JSON, nullable=True, default=None, comment="tool_calls数组，AI发起的工具调用请求列表"
        )
    )

    # 解析失败的非法工具调用，AIMessage.invalid_tool_calls
    invalid_tool_calls: list | None = Field(
        sa_column=Column(
            JSON,
            nullable=True,
            default=None,
            comment="invalid_tool_calls，解析异常、格式错误的工具调用",
        )
    )

    # 大模型侧返回的消息唯一ID
    message_id: str | None = Field(
        sa_column=Column(String(100), nullable=True, default=None, comment="大模型返回的消息唯一id")
    )


def ensure_created_after(message: Message, reference: Message) -> None:
    """保证 message 的 created_at 严格晚于 reference，至少相差 1 微秒。

    同一请求内成对写入 user/assistant 消息时，两次 default_factory 取到的
    时间戳可能落在同一微秒；消息列表仅按 created_at 排序，时间戳并列时
    数据库返回顺序不确定，会出现 assistant 排到 user 之前的乱序。
    """
    if message.created_at <= reference.created_at:
        message.created_at = reference.created_at + timedelta(microseconds=1)
