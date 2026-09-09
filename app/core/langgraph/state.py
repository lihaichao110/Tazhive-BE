from typing_extensions import NotRequired

from langchain.agents import AgentState


class ChatAgentState(AgentState):
    """create_agent 的状态扩展。

    messages（含 add_messages 累积语义）由父类 AgentState 提供，
    会话记忆由 checkpointer 按 thread_id 维护。以下为请求级字段：
    """

    model: NotRequired[str]
    """请求指定的模型名称，经 LLMRegistry 解析"""

    thinking: NotRequired[dict | None]
    """思考模式配置，透传给大模型（DeepSeek 的 {"type": "enabled"/"disabled"} 等）"""

    system_prompt: NotRequired[str]
    """系统提示词，缺省时 RagMiddleware 使用 SYSTEM_CHAT_PROMPT"""
