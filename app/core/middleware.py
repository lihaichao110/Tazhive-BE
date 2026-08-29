import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import logger

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 生成唯一请求 ID（可从请求头传入，否则生成）
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.time()

        # 将 request_id 存储到请求状态中，方便后续使用
        request.state.request_id = request_id

        # 记录请求开始
        logger.info(f"Request started: {request.method} {request.url.path} (request_id={request_id})")

        response = await call_next(request)

        # 记录请求完成
        process_time = time.time() - start_time
        logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"status={response.status_code} duration={process_time:.3f}s (request_id={request_id})"
        )

        # 在响应头中返回 request_id
        response.headers["X-Request-ID"] = request_id
        return response