from datetime import datetime, timezone
from uuid import uuid4
from sqlmodel import SQLModel, Field


class BaseModel(SQLModel):
    """
    数据库表通用基础模型，所有业务表继承该类，自动带上主键id、创建时间、更新时间字段
    SQLModel 融合 Pydantic 数据校验 + SQLAlchemy ORM数据库映射
    """

    # 主键ID，uuid4生成随机字符串，default_factory：插入数据时自动执行函数生成值，不写死默认常量
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    # 记录创建时间，默认生成 UTC 标准时区时间，新增记录自动填充，业务不要手动修改
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 记录更新时间，新建时和created_at一致；⚠注意：此处default_factory仅新增生效！
    # lambda只会在行插入的时候跑一遍，更新数据不会自动刷新时间，需要自己写触发器 / 业务代码手动赋值updated_at=datetime.now(timezone.utc)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))