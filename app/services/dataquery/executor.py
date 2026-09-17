"""校验通过的 SQL 的只读执行：行数上限、超时、结果 JSON 序列化。

会话模式与 plans/query.py 的 fetch_plan_shows 一致（自建 Session）。
配置 text2sql_readonly_database_url 后走惰性单例只读 engine，作为
sqlglot 白名单校验之外的兜底防护。
"""

import datetime as dt
import decimal
import json as jsonlib
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, create_engine

from app.core.config import settings
from app.core.logging import logger
from app.services.database import engine as default_engine

MAX_CELL_CHARS = 200
"""单个单元格序列化后的最大字符数，防止长文本把卡片与提示词撑爆。"""


@dataclass
class QueryOutcome:
    """一次查询的结果信封；error 非空表示失败，此时 rows 为空。"""

    columns: list[str] = field(default_factory=list)
    """结果列名，顺序与每行单元格对齐。"""

    rows: list[list[Any]] = field(default_factory=list)
    """行数据（已 JSON 序列化），每行是与 columns 对齐的单元格列表。"""

    truncated: bool = False
    """实际行数超过上限被截断时为 True。"""

    error: str | None = None
    """执行失败的简短说明（回喂给生成模型或回答模型）。"""


def _jsonable(value: Any) -> Any:
    """把数据库返回值转成 JSON 安全的基本类型并截断长文本。"""
    if isinstance(value, str):
        return value if len(value) <= MAX_CELL_CHARS else value[:MAX_CELL_CHARS] + "…"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")[:MAX_CELL_CHARS]
    if isinstance(value, (list, dict)):
        # json / jsonb 列由驱动解码为 list/dict，回转 JSON 文本便于展示
        payload = jsonlib.dumps(value, ensure_ascii=False, default=str)
        return payload if len(payload) <= MAX_CELL_CHARS else payload[:MAX_CELL_CHARS] + "…"
    return str(value)[:MAX_CELL_CHARS]


class QueryExecutor:
    """同步只读查询执行器；engine_override 供测试注入 SQLite 内存库。"""

    def __init__(
        self,
        *,
        max_rows: int | None = None,
        timeout_seconds: float | None = None,
        readonly_url: str | None = None,
        engine_override: Any | None = None,
    ):
        self._max_rows = max_rows
        self._timeout_seconds = timeout_seconds
        self._readonly_url = readonly_url
        self._engine_override = engine_override
        self._readonly_engine: Any | None = None

    def _resolve_engine(self) -> Any:
        if self._engine_override is not None:
            return self._engine_override
        url = (
            self._readonly_url
            if self._readonly_url is not None
            else settings.text2sql_readonly_database_url
        )
        if url:
            if self._readonly_engine is None:
                self._readonly_engine = create_engine(url, pool_pre_ping=True)
            return self._readonly_engine
        return default_engine

    def run(self, sql: str) -> QueryOutcome:
        max_rows = self._max_rows if self._max_rows is not None else settings.text2sql_max_rows
        try:
            with Session(self._resolve_engine()) as session:
                bind = session.get_bind()
                if bind is not None and bind.dialect.name == "postgresql":
                    timeout = (
                        self._timeout_seconds
                        if self._timeout_seconds is not None
                        else settings.text2sql_statement_timeout_seconds
                    )
                    # SET LOCAL 只在本事务内生效，会话结束即回滚，不影响连接池复用
                    session.execute(text(f"SET LOCAL statement_timeout = {int(timeout * 1000)}"))
                result = session.execute(text(sql))
                columns = list(result.keys())
                batch = result.fetchmany(max_rows + 1)
            truncated = len(batch) > max_rows
            rows = [[_jsonable(cell) for cell in row] for row in batch[:max_rows]]
            return QueryOutcome(columns=columns, rows=rows, truncated=truncated)
        except Exception as exc:
            logger.warning(
                "数据查询执行失败：error_type=%s detail=%s", type(exc).__name__, str(exc)[:200]
            )
            return QueryOutcome(error=f"{type(exc).__name__}: {str(exc)[:200]}")


default_executor = QueryExecutor()
"""生产默认执行器；参数在每次 run 时从 settings 现取，便于测试覆盖。"""

__all__ = ["MAX_CELL_CHARS", "QueryExecutor", "QueryOutcome", "default_executor"]
