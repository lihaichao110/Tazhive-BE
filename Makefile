# Makefile
.PHONY: help setup dev test lint lint-fix format-check format type-check clean-checkpoints migrate-gen migrate-up migrate-downgrade

help:
	@echo "可用命令："
	@echo "  make setup             安装依赖并启用 Git pre-commit hook"
	@echo "  make dev               启动开发服务器"
	@echo "  make test              运行测试"
	@echo "  make lint              运行代码检查"
	@echo "  make lint-fix          自动修复可安全处理的代码检查问题"
	@echo "  make format-check      检查代码格式"
	@echo "  make format            自动格式化代码"
	@echo "  make type-check        运行 mypy 类型检查（错误需人工修复）"
	@echo "  make migrate-up        初始化数据库（运行迁移）"
	@echo "  make clean-checkpoints 清理过期 checkpoint"

# 首次初始化开发环境，并让后续提交自动执行项目检查。
setup:
	uv sync
	uv run pre-commit install

# 自动生成迁移，用法：make migrate-gen msg="add user table"
migrate-gen:
	uv run alembic revision --autogenerate -m "$(msg)"

# 执行全部迁移到最新版本
migrate-up:
	uv run alembic upgrade head

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

format-check:
	uv run ruff format --check .

format:
	uv run ruff format .

# mypy 不提供通用自动修复，类型错误需根据检查结果人工处理。
type-check:
	uv run mypy app/

clean-checkpoints:
	uv run python scripts/clean_checkpoints.py 7
