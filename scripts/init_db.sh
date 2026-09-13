#!/usr/bin/env bash
set -e

echo "==> 运行数据库迁移..."
# 数据库配置既可来自 .env，也可由容器、CI 等运行环境直接注入。
uv run alembic upgrade head

echo "==> 数据库初始化完成。"
