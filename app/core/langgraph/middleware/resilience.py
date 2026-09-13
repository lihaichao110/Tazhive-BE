from collections.abc import Awaitable, Callable
from logging import getLogger
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.services.llm.registry import LLMRegistry, default_registry

logger = getLogger(__name__)


class ResilienceMiddleware(AgentMiddleware):
    """模型调用重试 + 注册表故障转移。

    迁移自原 llm_call 节点：tenacity 指数退避重试，每次失败后
    registry.rotate() 切换到下一个模型；下一次尝试会重新经过内层的
    ModelRoutingMiddleware 解析模型实例，因此切换立即生效。
    """

    def __init__(
        self,
        registry: LLMRegistry | None = None,
        max_attempts: int = 3,
        wait_min: float = 2.0,
        wait_max: float = 10.0,
    ):
        self.registry = registry or default_registry
        self.max_attempts = max_attempts
        self.wait_min = wait_min
        self.wait_max = wait_max

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        @retry(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(multiplier=1, min=self.wait_min, max=self.wait_max),
            retry=retry_if_exception_type(Exception),
            before_sleep=self._rotate_on_retry,
            reraise=True,
        )
        async def _call():
            return await handler(request)

        # tenacity 的 @retry 装饰器会丢失返回类型标注，这里显式断言。
        return cast(ModelResponse[Any], await _call())

    def _rotate_on_retry(self, retry_state) -> None:
        """重试前切换到注册表中的下一个模型（故障转移）"""
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(f"模型调用失败（第 {retry_state.attempt_number} 次）：{exc}，切换模型重试")
        self.registry.rotate()
