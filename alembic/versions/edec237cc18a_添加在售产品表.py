"""添加在售产品表

Revision ID: edec237cc18a
Revises: bbb7a18d70ba
Create Date: 2026-09-07 00:06:36.544126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'edec237cc18a'
down_revision: Union[str, Sequence[str], None] = 'bbb7a18d70ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('products',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False, comment='产品名称'),
    sa.Column('terms_url', sa.String(length=512), nullable=False, comment='产品条款 PDF 链接'),
    sa.Column('description_url', sa.String(length=512), nullable=True, comment='产品说明文档 PDF 链接（可空）'),
    sa.Column('additional_premium_rule_url', sa.String(length=512), nullable=True, comment='产品追加保险费规则 PDF 链接（可空）'),
    sa.Column('classification', sa.String(length=10), nullable=False, comment='产品分类分级 P1/P2/P3'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_products_classification'), 'products', ['classification'], unique=False)
    op.create_index(op.f('ix_products_name'), 'products', ['name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_products_name'), table_name='products')
    op.drop_index(op.f('ix_products_classification'), table_name='products')
    op.drop_table('products')
