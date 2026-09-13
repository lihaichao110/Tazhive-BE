from sqlalchemy import Column, String
from sqlmodel import Field

from app.models.base import BaseModel


class Product(BaseModel, table=True):
    """在售产品表，保存保险公司在售产品的名称、条款/说明文档链接及分类分级信息"""

    __tablename__ = "products"

    # 产品名称，建立索引便于按名称检索
    name: str = Field(sa_column=Column(String(255), index=True, nullable=False, comment="产品名称"))

    # 产品条款 PDF 链接
    terms_url: str = Field(
        sa_column=Column(String(512), nullable=False, comment="产品条款 PDF 链接")
    )

    # 产品说明文档 PDF 链接，个别产品无说明文档，可为空
    description_url: str | None = Field(
        sa_column=Column(String(512), nullable=True, comment="产品说明文档 PDF 链接（可空）")
    )

    # 产品追加保险费规则链接，部分产品无此规则，可为空
    additional_premium_rule_url: str | None = Field(
        sa_column=Column(String(512), nullable=True, comment="产品追加保险费规则 PDF 链接（可空）")
    )

    # 产品分类分级，取值 P1 / P2 / P3
    classification: str = Field(
        sa_column=Column(String(10), index=True, nullable=False, comment="产品分类分级 P1/P2/P3")
    )
