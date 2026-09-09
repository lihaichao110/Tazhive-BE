from pydantic import BaseModel
from typing import Optional, Dict, List, Any


class ChatRequest(BaseModel):
    """聊天请求入参模型
    接收前端传入的聊天提问内容
    """
    model: Optional[str] = None
    """前端指定模型，可忽略（后续可支持多模型）"""
    agent_id: Optional[str] = None
    """指定使用哪个 Agent"""
    thinking: Optional[Dict[str, Any]] = None
    """思考模式配置，透传给大模型（如 DeepSeek 的 {"type": "enabled"/"disabled"}）"""
    messages: List[Dict[str, Any]]
    """消息列表，格式如 [{"role": "user", "content": """
    # 可扩展其他字段，如 temperature 等
