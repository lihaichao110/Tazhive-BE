"""text2sql 数据查询服务：schema 文档、SQL 静态校验、只读执行与结果表格卡片。"""

from app.services.dataquery.executor import (
    QueryExecutor,
    QueryOutcome,
    default_executor,
)
from app.services.dataquery.guard import ALLOWED_TABLES, validate_sql
from app.services.dataquery.schema_doc import SQL_SCHEMA_DOC
from app.services.dataquery.x_card import (
    DATA_TABLE_COMPONENT,
    MAX_CARD_ROWS,
    build_table_envelope,
)

__all__ = [
    "ALLOWED_TABLES",
    "DATA_TABLE_COMPONENT",
    "MAX_CARD_ROWS",
    "QueryExecutor",
    "QueryOutcome",
    "SQL_SCHEMA_DOC",
    "build_table_envelope",
    "default_executor",
    "validate_sql",
]
