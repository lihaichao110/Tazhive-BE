from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from app.observability.metrics import LLM_CALL_COUNT, LLM_TOKEN_USED


class MetricsMiddleware(AgentMiddleware):
    """LLM 调用次数与 Token 消耗的 Prometheus 指标统计。

    放在中间件链最外层：只有模型调用成功返回后才计数，与原 llm_call
    节点的语义一致（彻底失败时异常直接向上冒泡，不计数）。
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        response = await handler(request)

        model_name = request.state.get("model") or "default"
        LLM_CALL_COUNT.labels(model=model_name).inc()

        # usage_metadata 挂在模型输出的 AIMessage 上，取最后一条带用量的消息
        for msg in reversed(response.result):
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                LLM_TOKEN_USED.labels(model=model_name, type="input").inc(
                    usage.get("input_tokens", 0)
                )
                LLM_TOKEN_USED.labels(model=model_name, type="output").inc(
                    usage.get("output_tokens", 0)
                )
                break

        return response
