"""补充投保流程字段注释

Revision ID: d6f82a1c4b73
Revises: f4b7d9e2c613
Create Date: 2026-09-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d6f82a1c4b73"
down_revision: str | Sequence[str] | None = "f4b7d9e2c613"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 注释与模型定义保持一致；集中维护便于 upgrade/downgrade 对称处理。
COLUMN_COMMENTS: dict[str, dict[str, str]] = {
    "insurance_applications": {
        "user_id": "发起投保流程的用户ID",
        "thread_id": "投保流程所属的会话ID",
        "group_code": "投保方案编码，关联plan_shows.group_code",
        "group_name": "发起投保时的方案名称快照",
        "plan_title": "发起投保时的方案分类名称快照",
        "insur_list_json": "发起投保时的险种代码列表JSON快照",
        "current_step": "当前流程步骤：APPLICANT_INFO/INSURED_INFO/PLAN_CONFIRMATION/CONFIRMED",
        "status": "投保状态：IN_PROGRESS进行中、CONFIRMED已确认",
        "version": "流程乐观锁版本号，用于识别过期操作",
        "consent_version": "用户同意的个人信息处理授权及投保须知版本",
        "consent_at": "用户同意个人信息处理授权及投保须知的时间",
        "confirmed_at": "用户确认投保方案的时间，未确认时为空",
    },
    "insurance_parties": {
        "application_id": "所属投保流程ID，关联insurance_applications.id",
        "party_type": "参与人类型：APPLICANT投保人、INSURED被保险人",
        "relationship": "投保人与被保险人的关系：SELF/SPOUSE/CHILD/PARENT",
        "encrypted_payload": "加密存储的参与人身份及联系方式JSON数据",
    },
    "insurance_events": {
        "event_id": "客户端生成的幂等事件UUID",
        "user_id": "触发事件的用户ID",
        "thread_id": "事件所属的会话ID",
        "application_id": "事件所属投保流程ID，关联insurance_applications.id",
        "event_name": "投保动作名称：plan_apply/applicant_submit/insured_submit/plan_confirm",
        "resulting_step": "事件处理完成后的投保流程步骤",
        "resulting_version": "事件处理完成后的投保流程版本号",
        "user_message_id": "事件生成的用户消息ID，关联messages.id",
        "assistant_message_id": "事件生成的助手消息ID，关联messages.id",
    },
}


def upgrade() -> None:
    """为已有投保业务表补充字段注释。"""
    for table_name, columns in COLUMN_COMMENTS.items():
        for column_name, comment in columns.items():
            op.alter_column(table_name, column_name, comment=comment, existing_comment=None)


def downgrade() -> None:
    """移除本迁移添加的字段注释。"""
    for table_name, columns in COLUMN_COMMENTS.items():
        for column_name, comment in columns.items():
            op.alter_column(table_name, column_name, comment=None, existing_comment=comment)
