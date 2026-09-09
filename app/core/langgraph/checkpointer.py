from app.core.config import settings
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from psycopg_pool import ConnectionPool, AsyncConnectionPool
from logging import getLogger
import aiosqlite

logger = getLogger(__name__)

def _is_sqlite() -> bool:
    """DATABASE_URL 是否指向 SQLite（如测试环境）"""
    return settings.database_url.startswith("sqlite")

def _sqlite_path() -> str:
    """提取 SQLite 数据库文件路径：sqlite:///./test.db -> ./test.db"""
    path = settings.database_url.split("///", 1)[-1]
    return path or ":memory:"

def _pg_conninfo() -> str:
    """psycopg 可用的连接串（database_url 若为 SQLAlchemy 方言格式需去掉 +psycopg 后缀）"""
    return settings.database_url.replace("+psycopg", "")

def _run_pg_migrations():
    """使用自动提交的临时连接池执行数据库迁移（解决 CREATE INDEX CONCURRENTLY 不能在事务中运行的问题）"""

    def configure_autocommit(conn):
        conn.autocommit = True

    # 临时池：仅用于执行 setup()，连接均为 autocommit
    temp_pool = ConnectionPool(
        conninfo=_pg_conninfo(),
        open=True,  # 立即打开连接
        min_size=1,
        max_size=1,  # 最大连接数
        configure=configure_autocommit      # 每个连接创建后自动设为 autocommit
    )

    try:
        # 创建 checkpointer 实例
        sync_saver = PostgresSaver(temp_pool)
        sync_saver.setup()
        logger.info("PostgresSaver OK")
    finally:
        temp_pool.close()


# 延迟创建异步资源（导入本模块不触发任何数据库连接）
_async_pool = None
_async_sqlite_conn = None
_async_checkpointer = None

async def get_async_checkpointer() -> BaseCheckpointSaver:
    """获取或创建异步 checkpointer 实例（应在事件循环内调用，按 DATABASE_URL 选择 SQLite/Postgres）"""
    global _async_pool, _async_sqlite_conn, _async_checkpointer
    if _async_checkpointer is None:
        if _is_sqlite():
            # SQLite：长连接 + AsyncSqliteSaver，setup() 建表（幂等）
            _async_sqlite_conn = await aiosqlite.connect(_sqlite_path())
            saver = AsyncSqliteSaver(_async_sqlite_conn)
            await saver.setup()
            _async_checkpointer = saver
            logger.info("AsyncSqliteSaver OK (%s)", _sqlite_path())
        else:
            # Postgres：先跑迁移，再建异步连接池
            _run_pg_migrations()
            # 创建异步连接池（open=False 不会立即打开）
            _async_pool = AsyncConnectionPool(
                conninfo=_pg_conninfo(),
                open=False,
                min_size=1,
                max_size=10,
            )
            # 手动打开连接池（需要事件循环）
            await _async_pool.open()
            # 创建异步 checkpointer
            _async_checkpointer = AsyncPostgresSaver(_async_pool)

    return _async_checkpointer

async def close_async_checkpointer() -> None:
    """关闭 checkpointer 持有的数据库资源（aiosqlite 连接线程非 daemon，不关闭会阻塞进程退出）"""
    global _async_pool, _async_sqlite_conn, _async_checkpointer
    if _async_sqlite_conn is not None:
        await _async_sqlite_conn.close()
        _async_sqlite_conn = None
    if _async_pool is not None:
        await _async_pool.close()
        _async_pool = None
    _async_checkpointer = None
