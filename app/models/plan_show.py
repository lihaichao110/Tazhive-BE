from sqlalchemy import Column, Integer, String, Text
from sqlmodel import JSON, Field

from app.models.base import BaseModel


class PlanShow(BaseModel, table=True):
    """方案展示表：把源 JSON 的 titleVos → planShowVos 两层结构拍平成的单表。

    每行 = 一个分类（title）下的一个方案分组（groupCode）。
    分类字段 title_id / title / title_ord_num 由父级 titleVos 冗余下来，不再单独建父表。

    ⚠ 已知的有损点：源 JSON 中 planShowVos 为空的分类（当前是「组合」titleId=4）
    不会产生任何行，扁平表无法表示「有分类但无方案」。因此从本表
    SELECT DISTINCT title_id, title, title_ord_num 只能拿到 4 个分类 tab，
    前端的 tab 列表需自行兜底（写死或另取静态配置）。
    """

    __tablename__ = "plan_shows"

    # 业务自然主键，对应JSON groupCode，导入脚本按它做幂等 upsert
    group_code: str = Field(
        sa_column=Column(
            String(64),
            index=True,
            unique=True,
            nullable=False,
            comment="方案分组编码，对应JSON groupCode，业务自然主键，全局唯一",
        )
    )

    # 方案名称，如「鸿利悠享2.0两全保险（分红型）」
    group_name: str = Field(
        sa_column=Column(String(255), nullable=False, comment="方案分组名称，对应JSON groupName")
    )

    # 多行卖点文案，源数据用 \r\n 分隔；长度不可控，必须用 Text
    contents: str | None = Field(
        sa_column=Column(
            Text, nullable=True, comment="方案卖点文案，多行文案以CRLF分隔，对应JSON contents；可空"
        )
    )

    # 方案在分类内的展示顺序，对应JSON orderNum；全局不唯一（源数据存在并列），仅用于排序
    order_num: int = Field(
        sa_column=Column(
            Integer,
            index=True,
            nullable=False,
            comment="分类内展示顺序，对应JSON orderNum；全局不唯一，排序用",
        )
    )

    # 所属分类ID，取自父级 titleVos.titleId
    title_id: int = Field(
        sa_column=Column(
            Integer, index=True, nullable=False, comment="所属分类ID，来自父级titleVos的titleId"
        )
    )

    # 所属分类名称，取自父级 titleVos.title
    title: str = Field(
        sa_column=Column(
            String(50), nullable=False, comment="所属分类名称，来自父级titleVos的title"
        )
    )

    # 分类展示顺序，取自父级 titleVos.ordNum；扁平表下排分类 tab 依赖它
    title_ord_num: int = Field(
        sa_column=Column(
            Integer,
            nullable=False,
            comment="分类展示顺序，来自父级titleVos的ordNum，分类Tab排序用",
        )
    )

    # 方案配图URL，由外部图标数据合并而来，可能缺失，故可为空
    img: str | None = Field(
        sa_column=Column(
            String(512), nullable=True, comment="方案配图URL，对应JSON img；外部图标可能缺失，可空"
        )
    )

    # 是否在售标识，源数据是字符串而非数字，保持原样以无损还原接口契约
    has_sale: str = Field(
        sa_column=Column(
            String(10), nullable=False, comment="是否在售标识，对应JSON hasSale，字符串取值1/2"
        )
    )

    # 关联险种代码数组，如 ["AYR","AYS","AYT"]
    insur_list: list[str] = Field(
        sa_column=Column(
            JSON,
            nullable=False,
            comment="关联险种代码数组，对应JSON insurList，如[AYR,AYS,AYT]",
        )
    )

    # 是否多险种投保，取值 0/1
    is_more_insur: int = Field(
        sa_column=Column(
            Integer, nullable=False, comment="是否多险种投保，对应JSON isMoreInsur，取值0/1"
        )
    )

    # 核保标识，取值 1/2，语义未知故保留原始整型
    is_approve: int = Field(
        sa_column=Column(Integer, nullable=False, comment="核保标识，对应JSON isApprove，取值1/2")
    )

    # 风险标识，对应JSON isIrisk，取值 1/2，语义未知故保留原始整型
    is_irisk: int = Field(
        sa_column=Column(Integer, nullable=False, comment="风险标识，对应JSON isIrisk，取值1/2")
    )
