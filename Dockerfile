# 使用官方 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖（如 libpq-dev 用于编译 PostgreSQL 相关包）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 固定 uv 版本，确保 Docker 和 CI 使用一致的锁文件解析行为
RUN pip install --no-cache-dir uv==0.11.26

# 复制项目配置文件
COPY pyproject.toml uv.lock ./

# 使用 uv 安装依赖到虚拟环境（--no-install-project 跳过构建项目本身，源码在最终阶段 COPY）
RUN uv sync --frozen --no-dev --no-install-project

# 使用虚拟环境中的 Python 作为运行时
FROM python:3.11-slim

WORKDIR /app

# 安装运行时 PostgreSQL 客户端库，并创建无登录权限的应用用户
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && rm -rf /var/lib/apt/lists/*

# 复制时直接设置所有者，避免后续递归 chown 再生成一个完整的虚拟环境镜像层。
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# 应用源码同样在复制时设置所有者；普通代码发布只会产生体积较小的源码层。
COPY --chown=appuser:appuser . .

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 上传文件只用于请求期间的临时解析。
RUN install -d -o appuser -g appuser uploads

USER appuser

# 暴露端口
EXPOSE 8000

# 数据库迁移由部署脚本在切换容器前执行，运行容器只负责提供 API。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
