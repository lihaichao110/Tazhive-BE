"""添加刷新令牌表

Revision ID: 9f3a2c1d84be
Revises: c8f41d9a6e20
Create Date: 2026-09-18 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f3a2c1d84be"
down_revision: str | Sequence[str] | None = "c8f41d9a6e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=64),
            nullable=False,
            comment="所属用户ID，关联users表主键id",
        ),
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
            comment="刷新令牌的SHA-256摘要",
        ),
        sa.Column(
            "expires_at", sa.DateTime(), nullable=False, comment="刷新令牌过期时间（naive UTC）"
        ),
        sa.Column(
            "revoked",
            sa.Boolean(),
            nullable=False,
            comment="是否已作废：轮换后旧令牌置True",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_refresh_tokens_token_hash"), "refresh_tokens", ["token_hash"], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_refresh_tokens_token_hash"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
