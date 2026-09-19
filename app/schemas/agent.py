from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """创建Agent请求体"""

    name: str
    """Agent名称"""
    description: str | None = None
    """Agent描述信息"""
    system_prompt: str | None = None
    """模型系统提示词"""
    model: str | None = None
    """调用的大模型标识；不传时使用 LLM_DEFAULT_MODEL"""
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    """模型温度；不传时使用 LLM_DEFAULT_TEMPERATURE"""


class AgentUpdate(BaseModel):
    """更新Agent请求体，字段不传则不修改"""

    name: str | None = None
    """Agent名称"""
    description: str | None = None
    """Agent描述信息"""
    system_prompt: str | None = None
    """模型系统提示词"""
    model: str | None = None
    """调用的大模型标识"""
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    """模型温度，控制生成随机性，取值0~2"""
    is_active: bool | None = None
    """Agent是否启用"""


class AgentRead(BaseModel):
    """Agent返回响应模型"""

    id: str
    """Agent唯一主键ID"""
    user_id: str
    """归属用户ID"""
    name: str
    """Agent名称"""
    description: str | None
    """Agent描述信息"""
    system_prompt: str | None
    """模型系统提示词"""
    model: str
    """调用的大模型标识"""
    temperature: float
    """模型温度，控制生成随机性，取值0~2"""
    is_active: bool
    """Agent是否启用"""
    created_at: datetime
    """创建时间"""
    updated_at: datetime
    """最后更新时间"""
