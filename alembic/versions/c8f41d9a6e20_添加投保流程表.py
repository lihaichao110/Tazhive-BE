"""添加投保流程、参与人和幂等事件表

Revision ID: c8f41d9a6e20
Revises: b7d2f4a91c63
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "c8f41d9a6e20"
down_revision: str | Sequence[str] | None = "b7d2f4a91c63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建投保业务表及幂等约束。"""
    op.create_table(
        "insurance_applications",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("group_code", sa.String(length=64), nullable=False),
        sa.Column("group_name", sa.String(length=255), nullable=False),
        sa.Column("plan_title", sa.String(length=50), nullable=False),
        sa.Column("insur_list_json", sa.Text(), nullable=False),
        sa.Column("current_step", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.String(length=32), nullable=True),
        sa.Column("consent_at", sa.DateTime(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("user_id", "thread_id", "group_code", "status"):
        op.create_index(
            op.f(f"ix_insurance_applications_{column}"), "insurance_applications", [column]
        )

    op.create_table(
        "insurance_parties",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("party_type", sa.String(length=20), nullable=False),
        sa.Column("relationship", sa.String(length=20), nullable=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "party_type"),
    )
    op.create_index(
        op.f("ix_insurance_parties_application_id"), "insurance_parties", ["application_id"]
    )

    op.create_table(
        "insurance_events",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("thread_id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("event_name", sa.String(length=50), nullable=False),
        sa.Column("resulting_step", sa.String(length=50), nullable=False),
        sa.Column("resulting_version", sa.Integer(), nullable=False),
        sa.Column("user_message_id", sa.String(length=64), nullable=False),
        sa.Column("assistant_message_id", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_insurance_events_event_id"), "insurance_events", ["event_id"], unique=True
    )
    for column in ("user_id", "thread_id", "application_id"):
        op.create_index(op.f(f"ix_insurance_events_{column}"), "insurance_events", [column])


def downgrade() -> None:
    """按依赖逆序删除投保业务表。"""
    op.drop_table("insurance_events")
    op.drop_table("insurance_parties")
    op.drop_table("insurance_applications")
