from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.router import api_router
from app.core.langgraph.checkpointer import close_async_checkpointer
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.middleware import RequestLoggingMiddleware
from app.observability.metrics import metrics_endpoint


# 启动时日志（可选）
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ========== 启动阶段：startup 逻辑 ==========
    logger.info("应用启动，初始化资源：数据库、连接池等")

    yield  # 应用正式运行，接收请求

    # ========== 关闭阶段：shutdown 逻辑 ==========
    await close_async_checkpointer()  # 释放 checkpointer 数据库连接，避免阻塞进程退出
    print("应用关闭，释放资源：关闭连接池、清理")


app = FastAPI(title="Agent API", version="0.1.0", description="FastAPI", lifespan=lifespan)

# 限流器必须挂载到 app.state，slowapi 依赖它
app.state.limiter = limiter
# slowapi 的限流处理器签名 (Request, RateLimitExceeded) 比 Starlette 期望的
# (Request, Exception) 更窄，属 slowapi 官方文档约定用法。
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# 添加请求日志中间件
app.add_middleware(RequestLoggingMiddleware)


# 添加 metrics 端点
@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_endpoint()


# 注册 v1 路由
app.include_router(api_router, prefix="/api/v1")
