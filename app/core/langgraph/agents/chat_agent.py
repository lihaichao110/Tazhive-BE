from langchain.agents import create_agent

from app.core.langgraph.checkpointer import get_async_checkpointer
from app.core.langgraph.middleware import (
    MetricsMiddleware,
    ModelRoutingMiddleware,
    RagMiddleware,
    ResilienceMiddleware,
    StreamingMiddleware,
)
from app.core.langgraph.state import ChatAgentState
from app.core.langgraph.tools import tools
from app.core.logging import logger
from app.services.llm.registry import default_registry

# 缓存编译后的 agent
_agent = None


async def get_chat_agent():
    """构建对话 Agent（create_agent 实现）。

    基础模型经 init_chat_model（LLMRegistry）创建后传给 create_agent；
    实际按请求路由的模型由 ModelRoutingMiddleware 在每次调用时覆盖。
    后续扩展只需：往 tools 里加工具，或往 middleware 列表里加中间件。

    中间件顺序（列表靠前为外层）：
    - Metrics       最外层，成功调用后统计 Prometheus 指标
    - Rag           检索一次并注入 system message（放在 Resilience 外，重试时不重复检索）
    - Resilience    tenacity 重试 + 失败时 registry.rotate() 故障转移
    - ModelRouting  每次调用按 state 解析模型（重试换模型由此生效）
    - Streaming     最内层，恢复 token 级流式（上游 create_agent 断链的 workaround，
                    见 streaming.py 说明；上游修复后可移除）
    """
    global _agent
    if _agent is None:
        checkpointer = await get_async_checkpointer()
        base_model = default_registry.get_model()

        _agent = create_agent(
            model=base_model,
            tools=tools,
            middleware=[
                MetricsMiddleware(),
                RagMiddleware(),
                ResilienceMiddleware(),
                ModelRoutingMiddleware(),
                StreamingMiddleware(),
            ],
            state_schema=ChatAgentState,
            checkpointer=checkpointer,
        )

        logger.info("Agent 用 create_agent 编译（工具 + 中间件）")
    return _agent
