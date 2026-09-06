from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class AgentCreate(BaseModel):
    """创建Agent请求体"""
    name: str
    """Agent名称"""
    description: Optional[str] = None
    """Agent描述信息"""
    system_prompt: Optional[str] = None
    """模型系统提示词"""
    model: str = "deepseek-v4-flash"
    """调用的大模型标识"""
    temperature: float = 0.7
    """模型温度，控制生成随机性，取值0~1"""


class AgentUpdate(BaseModel):
    """更新Agent请求体，字段不传则不修改"""
    name: Optional[str] = None
    """Agent名称"""
    description: Optional[str] = None
    """Agent描述信息"""
    system_prompt: Optional[str] = None
    """模型系统提示词"""
    model: Optional[str] = None
    """调用的大模型标识"""
    temperature: Optional[float] = None
    """模型温度，控制生成随机性，取值0~1"""
    is_active: Optional[bool] = None
    """Agent是否启用"""


class AgentRead(BaseModel):
    """Agent返回响应模型"""
    id: str
    """Agent唯一主键ID"""
    user_id: str
    """归属用户ID"""
    name: str
    """Agent名称"""
    description: Optional[str]
    """Agent描述信息"""
    system_prompt: Optional[str]
    """模型系统提示词"""
    model: str
    """调用的大模型标识"""
    temperature: float
    """模型温度，控制生成随机性，取值0~1"""
    is_active: bool
    """Agent是否启用"""
    created_at: datetime
    """创建时间"""
    updated_at: datetime
    """最后更新时间"""
