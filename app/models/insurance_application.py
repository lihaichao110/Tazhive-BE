"""投保流程持久化模型，不在聊天消息中保存个人敏感信息。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class InsuranceApplication(BaseModel, table=True):
    """一笔投保流程及其确定性步骤状态。"""

    __tablename__ = "insurance_applications"

    user_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    thread_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    group_code: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    group_name: str = Field(sa_column=Column(String(255), nullable=False))
    plan_title: str = Field(sa_column=Column(String(50), nullable=False))
    insur_list_json: str = Field(sa_column=Column(Text, nullable=False))
    current_step: str = Field(sa_column=Column(String(50), nullable=False))
    status: str = Field(sa_column=Column(String(50), index=True, nullable=False))
    version: int = Field(sa_column=Column(Integer, nullable=False, default=1))
    consent_version: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    consent_at: datetime | None = Field(default=None, sa_column=Column(DateTime(), nullable=True))
    confirmed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(), nullable=True))


class InsuranceParty(BaseModel, table=True):
    """投保参与人；身份资料整体加密后存储。"""

    __tablename__ = "insurance_parties"
    __table_args__ = (UniqueConstraint("application_id", "party_type"),)

    application_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    party_type: str = Field(sa_column=Column(String(20), nullable=False))
    relationship: str | None = Field(default=None, sa_column=Column(String(20), nullable=True))
    encrypted_payload: str = Field(sa_column=Column(Text, nullable=False))


class InsuranceEvent(BaseModel, table=True):
    """幂等事件记录，只保存安全元数据和已生成消息引用。"""

    __tablename__ = "insurance_events"

    event_id: str = Field(sa_column=Column(String(36), unique=True, index=True, nullable=False))
    user_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    thread_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    application_id: str = Field(sa_column=Column(String(64), index=True, nullable=False))
    event_name: str = Field(sa_column=Column(String(50), nullable=False))
    resulting_step: str = Field(sa_column=Column(String(50), nullable=False))
    resulting_version: int = Field(sa_column=Column(Integer, nullable=False))
    user_message_id: str = Field(sa_column=Column(String(64), nullable=False))
    assistant_message_id: str = Field(sa_column=Column(String(64), nullable=False))
