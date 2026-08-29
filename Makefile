# Makefile
.PHONY: migrate-gen migrate-up migrate-downgrade

# 自动生成迁移，用法：make migrate-gen msg="add user table"
migrate-gen:
	uv run alembic revision --autogenerate -m "$(msg)"

# 执行全部迁移到最新版本
migrate-up:
	uv run alembic upgrade head

# 回退上一个版本
migrate-downgrade:
	uv run alembic downgrade -1