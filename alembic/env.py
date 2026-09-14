import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

# 将项目根目录加入 sys.path，以便导入 app 模块
sys.path.append(str(Path(__file__).resolve().parents[2]))

# 导入模型模块的副作用会把所有业务表注册到 SQLModel.metadata，供 autogenerate 比对。
import app.models  # noqa: F401, E402
from app.core.config import settings  # noqa: E402

# 表面上变量没被使用，实际副作用：执行模型class定义，注册进SQLModel.metadata
# Alembic 就是读取这个 target_metadata 里面收集到的所有表结构，用来对比数据库，生成迁移脚本。

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 设置数据库连接字符串
config.set_main_option("sqlalchemy.url", settings.database_url)

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标元数据（SQLModel 的 metadata）
target_metadata = SQLModel.metadata

# LangGraph 的 checkpointer/store 在运行时用 setup() 幂等建表，不归 Alembic 管理。
# 它们不在 SQLModel.metadata 里，若不排除，每次 autogenerate 都会把它们当成
# schema drift 生成 op.drop_table()，一旦 upgrade 就会删掉线上会话状态。
LANGGRAPH_MANAGED_TABLES = frozenset(
    {
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
        "store",
        "store_migrations",
    }
)


def include_object(object_, name, type_, reflected, compare_to):
    """让 autogenerate 忽略 LangGraph 自建的表，其余对象照常比对。"""
    if type_ == "table" and name in LANGGRAPH_MANAGED_TABLES:
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
