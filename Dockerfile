# 使用官方 Python 3.11 slim 镜像作为基础
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装系统依赖（如 libpq 用于 psycopg）
# 先把 Debian 源换成清华镜像，避免国内访问 deb.debian.org 超时
RUN sed -i 's@deb.debian.org@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（同样走清华 PyPI 镜像）
RUN pip install --no-cache-dir uv -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目配置文件
COPY pyproject.toml uv.lock ./

# 使用 uv 安装依赖到虚拟环境（--no-install-project 跳过构建项目本身，源码在最终阶段 COPY）
RUN uv sync --frozen --no-dev --no-install-project

# 使用虚拟环境中的 Python 作为运行时
FROM python:3.11-slim

WORKDIR /app

# 安装运行所需的系统库
RUN sed -i 's@deb.debian.org@mirrors.tuna.tsinghua.edu.cn@g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制虚拟环境
COPY --from=builder /app/.venv /app/.venv

# 复制应用代码
COPY . .

# 设置环境变量
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# 创建上传目录
RUN mkdir -p uploads

# 暴露端口
EXPOSE 8000

# 启动命令（先运行迁移，再启动 uvicorn）
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]