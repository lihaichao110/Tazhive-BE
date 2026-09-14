"""添加方案展示表

Revision ID: b7d2f4a91c63
Revises: edec237cc18a
Create Date: 2026-09-14 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d2f4a91c63"
down_revision: str | Sequence[str] | None = "edec237cc18a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "plan_shows",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "group_code",
            sa.String(length=64),
            nullable=False,
            comment="方案分组编码，对应JSON groupCode，业务自然主键，全局唯一",
        ),
        sa.Column(
            "group_name",
            sa.String(length=255),
            nullable=False,
            comment="方案分组名称，对应JSON groupName",
        ),
        sa.Column(
            "contents",
            sa.Text(),
            nullable=True,
            comment="方案卖点文案，多行文案以CRLF分隔，对应JSON contents；可空",
        ),
        sa.Column(
            "order_num",
            sa.Integer(),
            nullable=False,
            comment="分类内展示顺序，对应JSON orderNum；全局不唯一，排序用",
        ),
        sa.Column(
            "title_id",
            sa.Integer(),
            nullable=False,
            comment="所属分类ID，来自父级titleVos的titleId",
        ),
        sa.Column(
            "title",
            sa.String(length=50),
            nullable=False,
            comment="所属分类名称，来自父级titleVos的title",
        ),
        sa.Column(
            "title_ord_num",
            sa.Integer(),
            nullable=False,
            comment="分类展示顺序，来自父级titleVos的ordNum，分类Tab排序用",
        ),
        sa.Column(
            "img",
            sa.String(length=512),
            nullable=True,
            comment="方案配图URL，对应JSON img；外部图标可能缺失，可空",
        ),
        sa.Column(
            "has_sale",
            sa.String(length=10),
            nullable=False,
            comment="是否在售标识，对应JSON hasSale，字符串取值1/2",
        ),
        sa.Column(
            "insur_list",
            sa.JSON(),
            nullable=False,
            comment="关联险种代码数组，对应JSON insurList，如[AYR,AYS,AYT]",
        ),
        sa.Column(
            "is_more_insur",
            sa.Integer(),
            nullable=False,
            comment="是否多险种投保，对应JSON isMoreInsur，取值0/1",
        ),
        sa.Column(
            "is_approve",
            sa.Integer(),
            nullable=False,
            comment="核保标识，对应JSON isApprove，取值1/2",
        ),
        sa.Column(
            "is_irisk", sa.Integer(), nullable=False, comment="风险标识，对应JSON isIrisk，取值1/2"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_plan_shows_group_code"), "plan_shows", ["group_code"], unique=True)
    op.create_index(op.f("ix_plan_shows_order_num"), "plan_shows", ["order_num"], unique=False)
    op.create_index(op.f("ix_plan_shows_title_id"), "plan_shows", ["title_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_plan_shows_title_id"), table_name="plan_shows")
    op.drop_index(op.f("ix_plan_shows_order_num"), table_name="plan_shows")
    op.drop_index(op.f("ix_plan_shows_group_code"), table_name="plan_shows")
    op.drop_table("plan_shows")
