from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """聊天请求入参模型
    接收前端传入的聊天提问内容
    """

    model: str | None = None
    """前端指定模型，可忽略（后续可支持多模型）"""
    agent_id: str | None = None
    """指定使用哪个 Agent"""
    thinking: dict[str, Any] | None = None
    """思考模式配置，透传给大模型（如 DeepSeek 的 {"type": "enabled"/"disabled"}）"""
    messages: list[dict[str, Any]]
    """消息列表，格式如 [{"role": "user", "content": """
    # 可扩展其他字段，如 temperature 等
