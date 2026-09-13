# Makefile
.PHONY: help dev test lint lint-fix clean-checkpoints migrate-gen migrate-up migrate-downgrade

help:
	@echo "可用命令："
	@echo "  make dev               启动开发服务器"
	@echo "  make test              运行测试"
	@echo "  make lint              运行代码检查"
	@echo "  make lint-fix          自动修复可安全处理的代码检查问题"
	@echo "  make migrate-up        初始化数据库（运行迁移）"
	@echo "  make clean-checkpoints 清理过期 checkpoint"

# 自动生成迁移，用法：make migrate-gen msg="add user table"
migrate-gen:
	uv run alembic revision --autogenerate -m "$(msg)"

# 执行全部迁移到最新版本
migrate-up:
	bash scripts/init_db.sh

# 回退上一个版本
migrate-downgrade:
	uv run alembic downgrade -1

# 开发热重载启动
dev:
	uv run uvicorn app.main:app --reload

# 普通启动（不重载，生产用）
run:
	uv run uvicorn app.main:app

# 数据集执行评测
eval-custom:
	uv run python -m app.evals.run_eval $(DATASET)

test:
	uv run pytest

lint:
	uv run ruff check .

# 仅应用 Ruff 标记为安全的修复，语义相关问题仍需人工处理。
lint-fix:
	uv run ruff check . --fix

clean-checkpoints:
	uv run python scripts/clean_checkpoints.py 7
