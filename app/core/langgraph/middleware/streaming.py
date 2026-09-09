"""token 级流式输出支持。

背景：langchain 1.3 的 create_agent 模型节点（trace=False）调用模型时不透传
RunnableConfig，导致回调链（on_chat_model_stream / on_llm_new_token）、
langgraph.config.get_config() 与 runtime.stream_writer 在模型调用处全部失效
（上游 issue：https://github.com/langchain-ai/langchain/issues/37869，1.4.0 仍未修复）。

本中间件通过两点恢复 token 流：
1. 调用模型前手动设置最小的 config contextvar（这是整条断链的根源），
   使 runtime.stream_writer 恢复可用；
2. 用 _TapRunnable 包装模型：内部改用 astream 流式消费，每个 chunk 通过
   stream_writer 以 custom 流发出（chat.py 用 astream(stream_mode=["custom",
   "messages"]) 接收），最后聚合 chunks 返回完整消息——聚合后 content /
   tool_calls / usage_metadata 均保留，不影响 create_agent 的工具调用循环。

上游修复后（模型节点透传 config），本中间件可直接从 middleware 列表移除，
chat.py 的接收逻辑无需变化。
"""

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.runnables.config import var_child_runnable_config
from langgraph.config import get_config
from langgraph.constants import CONF


def _ensure_config_context():
    """保证当前协程内 get_config() 可用。

    create_agent 的节点以 trace=False 执行，langgraph 不会设置 config
    contextvar；这里设置最小 config（checkpoint_ns 为空串表示根图），
    返回 reset token 供调用方恢复，若 contextvar 本就有值则返回 None。
    """
    try:
        get_config()
        return None
    except RuntimeError:
        return var_child_runnable_config.set({CONF: {"checkpoint_ns": ""}})


class _TapRunnable:
    """模型包装：流式消费并把 token chunk 通过 writer 转发，聚合返回完整消息。

    只需实现 bind / bind_tools / ainvoke（create_agent 的模型执行路径只用到
    这些）；chunk 聚合遵循 AIMessageChunk 的合并语义。
    """

    def __init__(self, runnable, writer):
        self._runnable = runnable
        self._writer = writer

    def bind_tools(self, tools, **kwargs):
        return _TapRunnable(self._runnable.bind_tools(tools, **kwargs), self._writer)

    def bind(self, **kwargs):
        return _TapRunnable(self._runnable.bind(**kwargs), self._writer)

    async def ainvoke(self, messages, config=None, **kwargs):
        final = None
        async for generation in self._runnable.astream(messages, config=config, **kwargs):
            chunk = generation.message if hasattr(generation, "message") else generation
            if self._writer is not None:
                self._writer(chunk)
            final = chunk if final is None else final + chunk
        return final


class StreamingMiddleware(AgentMiddleware):
    """恢复 token 级流式输出（配合 astream(stream_mode=["custom", ...])）。"""

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        token = _ensure_config_context()
        try:
            writer = getattr(request.runtime, "stream_writer", None)
            tapped = _TapRunnable(request.model, writer)
            return await handler(request.override(model=tapped))
        finally:
            if token is not None:
                var_child_runnable_config.reset(token)
