"""投保流程持久化模型，不在聊天消息中保存个人敏感信息。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlmodel import Field

from app.models.base import BaseModel


class InsuranceApplication(BaseModel, table=True):
    """一笔投保流程及其确定性步骤状态。"""

    __tablename__ = "insurance_applications"

    user_id: str = Field(
        sa_column=Column(String(64), index=True, nullable=False, comment="发起投保流程的用户ID")
    )
    thread_id: str = Field(
        sa_column=Column(String(64), index=True, nullable=False, comment="投保流程所属的会话ID")
    )
    group_code: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="投保方案编码，关联plan_shows.group_code",
        )
    )
    group_name: str = Field(
        sa_column=Column(String(255), nullable=False, comment="发起投保时的方案名称快照")
    )
    plan_title: str = Field(
        sa_column=Column(String(50), nullable=False, comment="发起投保时的方案分类名称快照")
    )
    insur_list_json: str = Field(
        sa_column=Column(Text, nullable=False, comment="发起投保时的险种代码列表JSON快照")
    )
    current_step: str = Field(
        sa_column=Column(
            String(50),
            nullable=False,
            comment="当前流程步骤：APPLICANT_INFO/INSURED_INFO/PLAN_CONFIRMATION/CONFIRMED",
        )
    )
    status: str = Field(
        sa_column=Column(
            String(50),
            index=True,
            nullable=False,
            comment="投保状态：IN_PROGRESS进行中、CONFIRMED已确认",
        )
    )
    version: int = Field(
        sa_column=Column(
            Integer, nullable=False, default=1, comment="流程乐观锁版本号，用于识别过期操作"
        )
    )
    consent_version: str | None = Field(
        default=None,
        sa_column=Column(
            String(32), nullable=True, comment="用户同意的个人信息处理授权及投保须知版本"
        ),
    )
    consent_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            DateTime(), nullable=True, comment="用户同意个人信息处理授权及投保须知的时间"
        ),
    )
    confirmed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(), nullable=True, comment="用户确认投保方案的时间，未确认时为空"),
    )


class InsuranceParty(BaseModel, table=True):
    """投保参与人；身份资料整体加密后存储。

    relationship 记录第一步采集的"投保人是被保人的"关系，APPLICANT 与 INSURED
    两行保存同值；选 SELF 时 INSURED 行直接复制投保人的加密资料。
    """

    __tablename__ = "insurance_parties"
    __table_args__ = (UniqueConstraint("application_id", "party_type"),)

    application_id: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="所属投保流程ID，关联insurance_applications.id",
        )
    )
    party_type: str = Field(
        sa_column=Column(
            String(20), nullable=False, comment="参与人类型：APPLICANT投保人、INSURED被保险人"
        )
    )
    relationship: str | None = Field(
        default=None,
        sa_column=Column(
            String(20),
            nullable=True,
            comment="投保人与被保险人的关系：SELF/SPOUSE/CHILD/PARENT",
        ),
    )
    encrypted_payload: str = Field(
        sa_column=Column(Text, nullable=False, comment="加密存储的参与人身份及联系方式JSON数据")
    )


class InsuranceEvent(BaseModel, table=True):
    """幂等事件记录，只保存安全元数据和已生成消息引用。"""

    __tablename__ = "insurance_events"

    event_id: str = Field(
        sa_column=Column(
            String(36), unique=True, index=True, nullable=False, comment="客户端生成的幂等事件UUID"
        )
    )
    user_id: str = Field(
        sa_column=Column(String(64), index=True, nullable=False, comment="触发事件的用户ID")
    )
    thread_id: str = Field(
        sa_column=Column(String(64), index=True, nullable=False, comment="事件所属的会话ID")
    )
    application_id: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            nullable=False,
            comment="事件所属投保流程ID，关联insurance_applications.id",
        )
    )
    event_name: str = Field(
        sa_column=Column(
            String(50),
            nullable=False,
            comment="投保动作名称：plan_apply/applicant_submit/insured_submit/plan_confirm",
        )
    )
    resulting_step: str = Field(
        sa_column=Column(String(50), nullable=False, comment="事件处理完成后的投保流程步骤")
    )
    resulting_version: int = Field(
        sa_column=Column(Integer, nullable=False, comment="事件处理完成后的投保流程版本号")
    )
    user_message_id: str = Field(
        sa_column=Column(
            String(64), nullable=False, comment="事件生成的用户消息ID，关联messages.id"
        )
    )
    assistant_message_id: str = Field(
        sa_column=Column(
            String(64), nullable=False, comment="事件生成的助手消息ID，关联messages.id"
        )
    )
