"""投保动作接口的安全请求和响应结构。"""

from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.message import MessageRead


class InsuranceActionRequest(BaseModel):
    """仅校验事件信封；含 PII 的 context 在服务层校验以避免默认错误回显。"""

    event_id: str
    """客户端为本次动作生成的唯一事件 ID，用于保证请求幂等性。"""
    name: Literal["plan_apply", "applicant_submit", "insured_submit", "plan_confirm"]
    """投保动作名称，分别对应开始投保、提交投保人、提交被保人和确认方案。"""
    source_surface_id: str
    """触发动作的前端交互卡片 ID，用于校验事件来源。"""
    application_id: str | None = None
    """投保申请 ID；开始投保时可不传，后续流程动作必须传入。"""
    expected_version: int | None = None
    """客户端预期的申请版本号，用于乐观锁并发校验。"""
    context: dict[str, Any]
    """动作上下文数据，可能包含个人敏感信息，由服务层按动作类型校验。"""


class InsuranceActionResponse(BaseModel):
    """动作成功后返回可直接追加到前端会话的两条持久化消息。"""

    outcome: Literal["advanced", "completed", "duplicate"]
    """动作处理结果：流程已推进、投保已完成或事件已重复处理。"""
    application_id: str
    """本次动作关联的投保申请 ID。"""
    current_step: str
    """动作处理完成后投保申请所处的流程步骤。"""
    version: int
    """动作处理完成后的申请版本号，供下一次请求进行并发校验。"""
    user_message: MessageRead
    """已持久化的用户操作摘要消息。"""
    assistant_message: MessageRead
    """已持久化的助手响应消息。"""
