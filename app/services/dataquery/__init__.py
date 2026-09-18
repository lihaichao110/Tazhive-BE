"""text2sql 数据查询服务：schema 文档、SQL 静态校验、只读执行与结果表格 Markdown。"""

from app.services.dataquery.executor import (
    QueryExecutor,
    QueryOutcome,
    default_executor,
)
from app.services.dataquery.guard import ALLOWED_TABLES, validate_sql
from app.services.dataquery.schema_doc import SQL_SCHEMA_DOC
from app.services.dataquery.table_markdown import (
    MAX_TABLE_ROWS,
    build_table_markdown,
    merge_table_into_envelope,
)

__all__ = [
    "ALLOWED_TABLES",
    "MAX_TABLE_ROWS",
    "QueryExecutor",
    "QueryOutcome",
    "SQL_SCHEMA_DOC",
    "build_table_markdown",
    "default_executor",
    "merge_table_into_envelope",
    "validate_sql",
]
