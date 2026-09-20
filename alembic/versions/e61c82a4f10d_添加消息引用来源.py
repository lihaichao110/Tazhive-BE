"""添加消息引用来源

Revision ID: e61c82a4f10d
Revises: 9f3a2c1d84be
Create Date: 2026-09-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e61c82a4f10d"
down_revision: str | Sequence[str] | None = "9f3a2c1d84be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "references",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
            comment="回答引用来源，支持 RAG 文档片段与联网搜索网页",
        ),
    )


def downgrade() -> None:
    op.drop_column("messages", "references")
