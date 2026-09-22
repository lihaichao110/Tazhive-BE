"""合并消息引用与模型名称迁移分支

Revision ID: f4b7d9e2c613
Revises: a3f9c2d8e741, e61c82a4f10d
Create Date: 2026-09-22 20:00:00.000000
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f4b7d9e2c613"
down_revision: str | Sequence[str] | None = ("a3f9c2d8e741", "e61c82a4f10d")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合并两条已有迁移分支，不额外修改数据库结构或数据。"""


def downgrade() -> None:
    """撤销合并节点，保留两条父迁移的结构和数据。"""
