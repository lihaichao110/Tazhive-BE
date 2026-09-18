from datetime import datetime

from sqlmodel import Boolean, Column, DateTime, Field, String

from app.models.base import BaseModel


class RefreshToken(BaseModel, table=True):
    """刷新令牌表，落地 refresh token 轮换状态，保证旧令牌单次有效"""

    __tablename__ = "refresh_tokens"

    # 所属用户ID，关联users表id；建立索引，便于按用户清理令牌
    user_id: str = Field(
        sa_column=Column(
            String(64), index=True, nullable=False, comment="所属用户ID，关联users表主键id"
        )
    )

    # 令牌SHA-256摘要，唯一索引用于快速定位；不存明文，防止拖库后直接冒用
    token_hash: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            unique=True,
            nullable=False,
            comment="刷新令牌的SHA-256摘要",
        )
    )

    # 令牌过期时间，与JWT exp声明一致；查询时兜底校验，也便于清理历史数据
    expires_at: datetime = Field(
        sa_column=Column(DateTime, nullable=False, comment="刷新令牌过期时间（naive UTC）")
    )

    # 是否已作废；轮换签发新令牌时置为True，旧令牌再次使用即拒绝
    revoked: bool = Field(
        sa_column=Column(
            Boolean, default=False, nullable=False, comment="是否已作废：轮换后旧令牌置True"
        )
    )
