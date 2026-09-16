"""保险投保确定性动作接口。"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.api.deps import get_current_user, get_db
from app.models.thread import Thread
from app.models.user import User
from app.schemas.insurance import InsuranceActionRequest, InsuranceActionResponse
from app.services.insurance import InsuranceFlowError, handle_insurance_action

router = APIRouter(prefix="/threads/{thread_id}/insurance", tags=["insurance"])


@router.post("/actions", response_model=InsuranceActionResponse)
def perform_insurance_action(
    thread_id: str,
    payload: Annotated[Any, Body()],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """校验线程归属后执行投保状态机，不调用意图分类器或大模型。"""
    thread = db.get(Thread, thread_id)
    if thread is None or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 在函数体内校验，避免 FastAPI 默认 422 把包含身份证号的原始输入回显给客户端。
    try:
        action = InsuranceActionRequest.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_event", "message": "投保事件格式不正确"},
        ) from exc
    try:
        return handle_insurance_action(db, action, user_id=current_user.id, thread_id=thread_id)
    except IntegrityError:
        # 并发重试可能同时越过首次幂等查询；唯一约束胜出后重新读取首次结果。
        db.rollback()
        try:
            return handle_insurance_action(db, action, user_id=current_user.id, thread_id=thread_id)
        except InsuranceFlowError as exc:
            db.rollback()
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except InsuranceFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
