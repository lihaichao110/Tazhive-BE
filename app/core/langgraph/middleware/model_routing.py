from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from app.services.llm.registry import LLMRegistry, default_registry


class ModelRoutingMiddleware(AgentMiddleware):
    """按请求解析实际使用的模型实例。

    chat.py 在输入 state 中携带 model（请求指定的模型名）与 thinking（思考模式
    配置），本中间件在每次模型调用时经 LLMRegistry（内部使用 init_chat_model）
    解析模型并注入请求。必须放在中间件链最内层：外层 ResilienceMiddleware
    重试时 handler 会重新经过这里，registry.rotate() 切换的模型才能生效。
    """

    def __init__(self, registry: LLMRegistry | None = None):
        self.registry = registry or default_registry

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        state = request.state
        model = self.registry.get_model(
            cast(str | None, state.get("model")),
            cast(dict | None, state.get("thinking")),
        )
        return await handler(request.override(model=model))
