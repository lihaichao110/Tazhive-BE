from typing_extensions import NotRequired

from langchain.agents import AgentState


class ChatAgentState(AgentState):
    """supervisor 图与各意图子 Agent 共用的状态定义。

    messages（含 add_messages 累积语义）由父类 AgentState 提供，
    会话记忆由 checkpointer 按 thread_id 维护。以下为请求级字段：
    """

    model: NotRequired[str]
    """请求指定的模型名称，经 LLMRegistry 解析"""

    thinking: NotRequired[dict | None]
    """思考模式配置，透传给大模型（DeepSeek 的 {"type": "enabled"/"disabled"} 等）"""

    system_prompt: NotRequired[str]
    """基础系统提示词；各意图 Agent 在模型调用前按注册表拼接自身协议"""

    intent: NotRequired[str]
    """意图识别结果（intent_node 写入），supervisor 按它路由到对应的子 Agent 节点"""

    intent_confidence: NotRequired[float]
    """意图分类置信度（0~1），目前仅随 SSE 广播给前端，不做控制"""
