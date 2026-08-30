from app.core.config import settings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool, AsyncConnectionPool
from logging import getLogger

logger = getLogger(__name__)

def _run_migrations():
    """使用自动提交的临时连接池执行数据库迁移（解决 CREATE INDEX CONCURRENTLY 不能在事务中运行的问题）"""

    def configure_autocommit(conn):
        conn.autocommit = True

    # 临时池：仅用于执行 setup()，连接均为 autocommit
    temp_pool = ConnectionPool(
        conninfo=settings.database_url,
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


# 先执行迁移（如果表已存在则跳过，幂等）
_run_migrations()

# 延迟创建异步资源
_async_pool = None
_async_checkpointer = None

async def get_async_checkpointer() -> AsyncPostgresSaver:
    """获取或创建异步 checkpointer 实例（应在事件循环内调用）"""
    global _async_pool, _async_checkpointer
    if _async_checkpointer is None:
        # 创建异步连接池（open=False 不会立即打开）
        _async_pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            open=False,
            min_size=1,
            max_size=10,
        )
        # 手动打开连接池（需要事件循环）
        await _async_pool.open()
        # 创建异步 checkpointer
        _async_checkpointer = AsyncPostgresSaver(_async_pool)

    return _async_checkpointer

logger.info("Checkpointer 模块初始化（异步保存程序延迟）")
