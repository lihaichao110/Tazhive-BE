from sqlalchemy import Boolean, Column, Float, String
from sqlmodel import Field

from app.models.base import BaseModel


class Agent(BaseModel, table=True):
    __tablename__ = "agents"

    user_id: str = Field(
        sa_column=Column(String(), index=True, nullable=False, comment="属于哪个用户")
    )
    name: str = Field(sa_column=Column(String(100), nullable=False, comment="Agent名称"))
    description: str | None = Field(
        sa_column=Column(String(500), nullable=True, comment="Agent描述信息")
    )
    system_prompt: str | None = Field(
        sa_column=Column(String(), nullable=True, comment="系统提示词")
    )
    model: str = Field(
        sa_column=Column(
            String(100), nullable=False, default="deepseek-v4-flash", comment="使用的模型标识"
        )
    )
    temperature: float = Field(
        sa_column=Column(Float(), nullable=False, default=0.7, comment="模型温度参数")
    )
    is_active: bool = Field(
        sa_column=Column(Boolean(), nullable=False, default=True, comment="是否启用")
    )
