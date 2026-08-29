from sqlmodel import Field, Column, String, Boolean
from app.models.base import BaseModel


class User(BaseModel, table=True):
    """用户表，存储系统账号信息"""
    __tablename__ = "users"

    username: str = Field(
        sa_column=Column(
            String(128),
            index=True,
            unique=True,
            nullable=False,
            comment="登录用户名，全局唯一"
        )
    )

    email: str = Field(
        sa_column=Column(
            String(255),
            index=True,
            unique=True,
            nullable=False,
            comment="用户邮箱，用于登录、找回密码"
        )
    )

    hashed_password: str = Field(
        sa_column=Column(
            String(255),
            nullable=False,
            comment="bcrypt哈希后的密码，禁止存储明文"
        )
    )

    is_active: bool = Field(
        sa_column=Column(
            Boolean,
            default=True,
            nullable=False,
            comment="账号是否启用，false代表禁用账号"
        )
    )

    is_superuser: bool = Field(
        sa_column=Column(
            Boolean,
            default=False,
            nullable=False,
            comment="是否超级管理员，拥有全部后台权限"
        )
    )
