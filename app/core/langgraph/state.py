from typing import Annotated, TypedDict
from operator import add
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    # 普通列表：每次节点返回的 messages 会覆盖旧值
    messages: list[BaseMessage]
    # 检索发现等累加信息
    findings: Annotated[list[str], add]
    # 错误记录（累加）
    errors: Annotated[list[str], add]
    # 模型名称
    model: str
    # 普通字段（会被覆盖）
    current_step: str
    document_ids: list[str]
    approved: bool
    # 思考模式配置，透传给大模型（DeepSeek 的 {"type": "enabled"/"disabled"} 等）
    thinking: dict | None