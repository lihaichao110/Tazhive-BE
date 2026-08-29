from sqlmodel import Field, Column, String
from app.models.base import BaseModel


class Thread(BaseModel, table=True):
    """对话会话表，保存每一轮Agent对话会话，一个用户可以拥有多个会话"""
    __tablename__ = "threads"

    # 所属用户ID，关联users表id；建立索引，方便按用户查询全部会话
    user_id: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="所属用户ID，关联users表主键id"
        )
    )

    # 会话标题，可以为空；最大长度255字符，用户可自定义会话标题
    title: str | None = Field(
        sa_column=Column(
            String(255),
            default=None,
            nullable=True,
            comment="对话会话标题，允许为空"
        )
    )

    # 会话状态：active正常使用 / archived归档 / deleted逻辑删除
    status: str = Field(
        sa_column=Column(
            String(50),
            default="active",
            nullable=False,
            comment="会话状态：active正常、archived归档、deleted逻辑删除"
        )
    )
