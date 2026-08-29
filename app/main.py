from fastapi import FastAPI
from app.api.v1.router import api_router
from app.core.middleware import RequestLoggingMiddleware
from contextlib import asynccontextmanager
from app.core.logging import logger

# 启动时日志（可选）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== 启动阶段：startup 逻辑 ==========
    logger.info("应用启动，初始化资源：数据库、连接池等")

    yield  # 应用正式运行，接收请求

    # ========== 关闭阶段：shutdown 逻辑 ==========
    print("应用关闭，释放资源：关闭连接池、清理")

app = FastAPI(
    title="Agent API",
    version="0.1.0",
    description="FastAPI",
    lifespan=lifespan
)

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 注册 v1 路由
app.include_router(api_router, prefix="/api/v1")
