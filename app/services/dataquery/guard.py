"""生成 SQL 的静态校验与归一化，text2sql 的核心安全层。

规则：Postgres 方言解析、仅允许单条只读 SELECT（含 CTE / UNION）、表名白名单、
危险函数黑名单、树中不得出现任何写操作节点、强制 LIMIT 上限。
校验通过时返回 sqlglot 归一化后的 SQL 文本，失败时返回中文错误说明，
供执行前拦截与回喂给生成模型重试。
"""

import sqlglot
from sqlglot import exp

from app.core.config import settings

ALLOWED_TABLES = frozenset(
    {
        "products",
        "plan_shows",
        "insurance_applications",
        "insurance_events",
    }
)
"""表名白名单：与 schema_doc.py 描述的表集合保持一致。"""

DENIED_FUNCTIONS = frozenset(
    {
        # 睡眠 / 资源占用
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        # 服务端文件系统读写
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        # 跨连接 / 运维管理
        "dblink",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_switch_wal",
        "pg_logical_emit_message",
        # 序列推进（副作用写）
        "setval",
    }
)

# 树中任何位置（含 CTE 子查询）都不允许出现的写操作 / 管理节点类型名
_DENIED_NODE_TYPE_NAMES = frozenset(
    {
        "Insert",
        "Update",
        "Delete",
        "Merge",
        "Create",
        "Drop",
        "Alter",
        "TruncateTable",
        "Grant",
        "Command",
    }
)


def _check_tables(stmt: exp.Query) -> str | None:
    # CTE 别名也会被解析成 Table 节点，先收集名单放行（仅限本语句内部定义）
    cte_names = {cte.alias_or_name.lower() for cte in stmt.find_all(exp.CTE)}
    for table in stmt.find_all(exp.Table):
        name = table.name.strip('"').lower()
        if not name:
            return "存在无法识别表名的查询目标（可能是函数表或元查询），不允许执行"
        if name in cte_names:
            continue
        if name not in ALLOWED_TABLES:
            return f"不允许查询表 {name}，可查询的表只有：{', '.join(sorted(ALLOWED_TABLES))}"
    return None


def _check_functions(stmt: exp.Query) -> str | None:
    for func in stmt.find_all(exp.Func):
        name = (str(func.this) if isinstance(func, exp.Anonymous) else func.sql_name()).lower()
        if name in DENIED_FUNCTIONS:
            return f"不允许使用函数 {name}"
    return None


def _check_write_nodes(stmt: exp.Query) -> str | None:
    for node in stmt.walk():
        if type(node).__name__ in _DENIED_NODE_TYPE_NAMES:
            return f"不允许执行 {type(node).__name__.upper()} 等写操作或管理语句"
    return None


def _enforce_limit(stmt: exp.Query, max_rows: int) -> exp.Query:
    """无 LIMIT 或 LIMIT 超上限（或非字面量）时强制改为上限。"""
    current = stmt.args.get("limit")
    if current is not None:
        literal = current.expression
        if isinstance(literal, exp.Literal) and literal.is_number:
            try:
                if int(literal.this) <= max_rows:
                    return stmt
            except (TypeError, ValueError):
                pass
    return stmt.limit(max_rows, copy=False)


def validate_sql(sql: str, *, max_rows: int | None = None) -> tuple[str, str | None]:
    """校验模型生成的 SQL；返回 (归一化 SQL, 错误说明)，错误为 None 表示通过。"""
    if not sql or not sql.strip():
        return sql, "SQL 为空"
    limit_cap = max_rows if max_rows is not None else settings.text2sql_max_rows

    try:
        statements = [item for item in sqlglot.parse(sql, read="postgres") if item is not None]
    except Exception as exc:  # sqlglot 抛的 ParseError 等都归为解析失败
        return sql, f"SQL 解析失败：{str(exc).splitlines()[0][:200]}"

    if len(statements) != 1:
        return sql, f"仅允许单条 SQL 语句，当前解析出 {len(statements)} 条"
    stmt = statements[0]

    # 只放行查询类根节点（SELECT / UNION / 括号子查询）；INSERT、SET、COPY、
    # EXPLAIN 等都会解析成非 Query 节点，直接拒绝。
    if not isinstance(stmt, exp.Query):
        return sql, f"仅允许 SELECT 查询，当前语句类型是 {type(stmt).__name__}"

    error = _check_write_nodes(stmt) or _check_tables(stmt) or _check_functions(stmt)
    if error:
        return sql, error

    stmt = _enforce_limit(stmt, limit_cap)
    return stmt.sql(dialect="postgres"), None


__all__ = ["ALLOWED_TABLES", "DENIED_FUNCTIONS", "validate_sql"]
