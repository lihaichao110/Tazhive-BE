"""统一 Agent 模型名称

Revision ID: a3f9c2d8e741
Revises: c8f41d9a6e20
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c2d8e741"
down_revision: str | Sequence[str] | None = "c8f41d9a6e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """将已保存的旧模型名迁移为统一的规范名称。"""
    op.execute(
        sa.text("UPDATE agents SET model = 'deepseek-flash' WHERE model = 'deepseek-v4-flash'")
    )


def downgrade() -> None:
    """回退到旧版模型名称。"""
    op.execute(
        sa.text("UPDATE agents SET model = 'deepseek-v4-flash' WHERE model = 'deepseek-flash'")
    )
