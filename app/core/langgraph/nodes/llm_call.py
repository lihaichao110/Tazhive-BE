from logging import getLogger
from langchain_core.runnables import RunnableConfig
from app.core.langgraph import AgentState
from app.core.langgraph.prompts.system_chat import SYSTEM_CHAT_PROMPT
from langchain_core.messages import SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.llm.registry import default_registry

logger = getLogger(__name__)

# 模型缓存，避免每次请求都新建
_model_cache = {}

async def _invoke_with_retry(model, messages, config: RunnableConfig, **kwargs):
    """带重试的模型调用（适用于网络异常等），返回累积后的完整回复消息。

    注意：model.astream() 返回的是异步生成器（AsyncIterator），不能被 await，
    必须在函数内部用 async for 迭代并累积成完整消息后返回。

    kwargs 会透传给模型调用（例如 extra_body），用于控制思考模式等厂商特有参数。
    """
    @retry(
        stop=stop_after_attempt(3),     # 总共最多执行 3 次
        wait=wait_exponential(multiplier=1, min=2, max=10), # 指数退避策略
        retry=retry_if_exception_type(Exception)  # 什么异常才触发重试
    )
    async def _call():
        response = None
        async for chunk in model.astream(messages, config=config, **kwargs):
            response = chunk if response is None else response + chunk
        return response

    return await _call()


async def llm_call(state: AgentState, config: RunnableConfig) -> dict:
    """
    节点：调用 LLM 生成回复
    输入 state["messages"] 是前端传来的完整对话历史（包含用户和助手消息）。
    输出新的完整消息列表（原始历史 + 新助手消息）。

    注意：必须接收并把运行时 config 透传给模型调用，否则模型产生的
    on_chat_model_stream / on_chat_model_end 等回调事件不会向上传播到
    graph.astream_events，chat.py 里的流式循环就拿不到任何内容。
    """
    model_name = state.get("model")
    # 从注册表获取模型（可能轮询）
    llm = default_registry.get_model(model_name)
    # 获取原始历史
    history = state["messages"]

    # 添加系统提示（放在最前面）
    messages = [SystemMessage(content=SYSTEM_CHAT_PROMPT)] + history

    # 透传思考模式配置：DeepSeek 等通过 extra_body={"thinking": {...}} 控制思考开关，
    # 前端传 {"type": "disabled"} 即关闭思考、{"type": "enabled"} 开启思考。
    invoke_kwargs = {}
    thinking = state.get("thinking")
    if thinking:
        invoke_kwargs["extra_body"] = {"thinking": thinking}

    # 使用 astream 流式调用，并透传 config：
    # 1) 只有流式调用才会触发 on_chat_model_stream 事件；
    # 2) config 透传才能把这些事件向上冒泡到 agent.astream_events。
    logger.info(f'state: {state}')
    try:
        response = await _invoke_with_retry(llm, messages, config, **invoke_kwargs)
    except Exception as e:
        logger.error(f'模型调用失败：{e}')
        # 如果当前模型失败，尝试切换到下一个并再次调用
        default_registry.rotate()
        model = default_registry.get_model()
        response = await _invoke_with_retry(model, messages, config, **invoke_kwargs)

    # 返回完整历史 + 助手回复；由于 messages 是普通列表，会覆盖状态中的 messages
    return {"messages": history + [response]}