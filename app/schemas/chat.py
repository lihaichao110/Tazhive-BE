from pydantic import BaseModel
from typing import Optional, Dict, List, Any


class ChatRequest(BaseModel):
    """聊天请求入参模型
    接收前端传入的聊天提问内容
    """
    model: Optional[str] = None
    """前端指定模型，可忽略（后续可支持多模型）"""
    stream: bool = False
    """是否流式返回"""
    thinking: Optional[Dict[str, Any]] = None
    """思考模式配置，透传给大模型（如 DeepSeek 的 {"type": "enabled"/"disabled"}）"""
    messages: List[Dict[str, Any]]
    """消息列表，格式如 [{"role": "user", "content": """
    # 可扩展其他字段，如 temperature 等


class ChatResponse(BaseModel):
    """
    兼容 OpenAI 格式的对话大模型非流式返回响应体
    非流式响应：返回完整的助手消息对象和可能的附加信息
    """
    # 请求唯一标识ID
    id: str
    # 对象类型，固定为 chat.completion 代表对话补全非流式响应
    object: str = "chat.completion"
    # Unix 时间戳，响应生成时间
    created: int
    # 使用的模型名称
    model: str
    # 模型返回结果列表，包含消息内容、finish_reason、索引等信息
    choices: List[Dict[str, Any]]
    # token 使用统计，包含输入、输出、总token数，可选字段
    usage: Optional[Dict[str, Any]] = None
