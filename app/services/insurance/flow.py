"""投保动作的确定性状态机、事务持久化与安全消息生成。"""

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlmodel import Session, select

from app.core.config import settings
from app.models.insurance_application import InsuranceApplication, InsuranceEvent, InsuranceParty
from app.models.message import Message
from app.models.plan_show import PlanShow
from app.schemas.insurance import InsuranceActionRequest, InsuranceActionResponse
from app.schemas.message import MessageRead
from app.services.insurance.security import PIICipher, mask_id_number, mask_mobile, mask_name
from app.services.insurance.validation import RELATIONSHIPS, validate_person_form
from app.services.insurance.x_card import (
    build_applicant_form,
    build_completion,
    build_insured_form,
    build_plan_confirmation,
)
from app.services.plans import format_a2ui_fence

APPLICANT_INFO = "APPLICANT_INFO"
INSURED_INFO = "INSURED_INFO"
PLAN_CONFIRMATION = "PLAN_CONFIRMATION"
CONFIRMED = "CONFIRMED"
CONSENT_VERSION = "v1"

# 动作处理结果，与 InsuranceActionResponse.outcome 的取值保持一致。
Outcome = Literal["advanced", "completed", "duplicate"]


class InsuranceFlowError(RuntimeError):
    """可安全返回前端的业务错误，不携带原始个人资料。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        field_errors: dict[str, str] | None = None,
        current_step: str | None = None,
        version: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail: dict[str, Any] = {"code": code, "message": message}
        if field_errors:
            self.detail["field_errors"] = field_errors
        if current_step is not None:
            self.detail["current_step"] = current_step
        if version is not None:
            self.detail["version"] = version


def _message_read(message: Message) -> MessageRead:
    return MessageRead.model_validate(message, from_attributes=True)


def _validate_envelope(payload: InsuranceActionRequest) -> None:
    try:
        UUID(payload.event_id)
    except (ValueError, AttributeError) as exc:
        raise InsuranceFlowError(400, "invalid_event", "event_id 必须是有效的 UUID") from exc
    if not payload.source_surface_id.strip():
        raise InsuranceFlowError(400, "invalid_event", "source_surface_id 不能为空")


def _find_duplicate(
    session: Session, payload: InsuranceActionRequest, user_id: str, thread_id: str
) -> InsuranceActionResponse | None:
    event = session.exec(
        select(InsuranceEvent).where(InsuranceEvent.event_id == payload.event_id)
    ).first()
    if event is None:
        return None
    if event.user_id != user_id or event.thread_id != thread_id or event.event_name != payload.name:
        raise InsuranceFlowError(409, "event_conflict", "该事件标识已被使用")
    user_message = session.get(Message, event.user_message_id)
    assistant_message = session.get(Message, event.assistant_message_id)
    if user_message is None or assistant_message is None:
        raise InsuranceFlowError(409, "event_conflict", "重复事件的原始响应不可用")
    return InsuranceActionResponse(
        outcome="duplicate",
        application_id=event.application_id,
        current_step=event.resulting_step,
        version=event.resulting_version,
        user_message=_message_read(user_message),
        assistant_message=_message_read(assistant_message),
    )


def _load_application(
    session: Session, payload: InsuranceActionRequest, user_id: str, thread_id: str
) -> InsuranceApplication:
    if not payload.application_id or payload.expected_version is None:
        raise InsuranceFlowError(400, "invalid_event", "缺少 application_id 或 expected_version")
    application = session.get(InsuranceApplication, payload.application_id)
    if application is None or application.user_id != user_id or application.thread_id != thread_id:
        raise InsuranceFlowError(404, "application_not_found", "投保流程不存在")
    if application.version != payload.expected_version:
        raise InsuranceFlowError(
            409,
            "stale_step",
            "该投保步骤已更新，请使用最新卡片继续",
            current_step=application.current_step,
            version=application.version,
        )
    return application


def _load_party(session: Session, application_id: str, party_type: str) -> InsuranceParty:
    party = session.exec(
        select(InsuranceParty).where(
            InsuranceParty.application_id == application_id,
            InsuranceParty.party_type == party_type,
        )
    ).first()
    if party is None:
        raise InsuranceFlowError(409, "incomplete_application", "投保资料不完整，请重新填写")
    return party


def _masked_person(cipher: PIICipher, party: InsuranceParty) -> dict[str, str]:
    value = cipher.decrypt(party.encrypted_payload)
    return {
        "name": mask_name(value["name"]),
        "mobile": mask_mobile(value["mobile"]),
        "id_number": mask_id_number(value["id_number"]),
    }


def _response_messages(
    *,
    thread_id: str,
    user_summary: str,
    assistant_text: str,
    envelope: dict[str, Any],
) -> tuple[Message, Message]:
    user_message = Message(thread_id=thread_id, role="user", content=user_summary)
    assistant_message = Message(
        thread_id=thread_id,
        role="assistant",
        content=f"{assistant_text}{format_a2ui_fence(envelope)}",
    )
    return user_message, assistant_message


def _handle_plan_apply(
    session: Session, payload: InsuranceActionRequest, user_id: str, thread_id: str
) -> tuple[InsuranceApplication, str, str, dict[str, Any], Outcome]:
    group_code = payload.context.get("group_code")
    if not isinstance(group_code, str) or not group_code.strip():
        raise InsuranceFlowError(422, "validation_failed", "请选择有效的保险方案")
    plan = session.exec(select(PlanShow).where(PlanShow.group_code == group_code.strip())).first()
    if plan is None:
        raise InsuranceFlowError(404, "plan_not_found", "所选保险方案不存在")
    application = InsuranceApplication(
        user_id=user_id,
        thread_id=thread_id,
        group_code=plan.group_code,
        group_name=plan.group_name,
        plan_title=plan.title,
        insur_list_json=json.dumps(plan.insur_list, ensure_ascii=False),
        current_step=APPLICANT_INFO,
        status="IN_PROGRESS",
        version=1,
    )
    session.add(application)
    envelope = build_applicant_form(
        application_id=application.id,
        version=application.version,
        catalog_id=settings.plan_show_catalog_id,
    )
    return (
        application,
        f"已选择「{plan.group_name}」正式投保",
        "请先填写投保人信息。",
        envelope,
        "advanced",
    )


def _handle_applicant(
    session: Session,
    payload: InsuranceActionRequest,
    cipher: PIICipher,
    user_id: str,
    thread_id: str,
) -> tuple[InsuranceApplication, str, str, dict[str, Any], Outcome]:
    application = _load_application(session, payload, user_id, thread_id)
    if application.current_step != APPLICANT_INFO:
        raise InsuranceFlowError(
            409,
            "stale_step",
            "请使用最新投保步骤继续",
            current_step=application.current_step,
            version=application.version,
        )
    form = payload.context.get("form")
    person, errors = validate_person_form(form)
    if not isinstance(form, dict) or form.get("consent") is not True:
        errors["consent"] = "请阅读并同意个人信息处理授权及投保须知"
    if errors or person is None:
        raise InsuranceFlowError(422, "validation_failed", "请检查投保人信息", field_errors=errors)
    party = InsuranceParty(
        application_id=application.id,
        party_type="APPLICANT",
        encrypted_payload=cipher.encrypt(person),
    )
    session.add(party)
    application.current_step = INSURED_INFO
    application.version = 2
    application.consent_version = CONSENT_VERSION
    application.consent_at = datetime.now(UTC)
    application.updated_at = datetime.now(UTC)
    applicant_masked = _masked_person(cipher, party)
    envelope = build_insured_form(
        application_id=application.id,
        version=application.version,
        applicant_masked=applicant_masked,
        catalog_id=settings.plan_show_catalog_id,
    )
    return (
        application,
        "已提交投保人信息",
        "投保人信息已保存，请填写被保险人信息。",
        envelope,
        "advanced",
    )


def _handle_insured(
    session: Session,
    payload: InsuranceActionRequest,
    cipher: PIICipher,
    user_id: str,
    thread_id: str,
) -> tuple[InsuranceApplication, str, str, dict[str, Any], Outcome]:
    application = _load_application(session, payload, user_id, thread_id)
    if application.current_step != INSURED_INFO:
        raise InsuranceFlowError(
            409,
            "stale_step",
            "请使用最新投保步骤继续",
            current_step=application.current_step,
            version=application.version,
        )
    form = payload.context.get("form")
    relationship = form.get("relationship") if isinstance(form, dict) else None
    if relationship not in RELATIONSHIPS:
        raise InsuranceFlowError(
            422,
            "validation_failed",
            "请检查被保险人信息",
            field_errors={"relationship": "请选择与投保人的关系"},
        )
    applicant = _load_party(session, application.id, "APPLICANT")
    if relationship == "SELF":
        encrypted_payload = applicant.encrypted_payload
    else:
        person, errors = validate_person_form(form)
        if errors or person is None:
            raise InsuranceFlowError(
                422, "validation_failed", "请检查被保险人信息", field_errors=errors
            )
        encrypted_payload = cipher.encrypt(person)
    insured = InsuranceParty(
        application_id=application.id,
        party_type="INSURED",
        relationship=relationship,
        encrypted_payload=encrypted_payload,
    )
    session.add(insured)
    application.current_step = PLAN_CONFIRMATION
    application.version = 3
    application.updated_at = datetime.now(UTC)
    summary = {
        "groupName": application.group_name,
        "title": application.plan_title,
        "insurList": json.loads(application.insur_list_json),
        "applicant": _masked_person(cipher, applicant),
        "insured": _masked_person(cipher, insured),
        "relationship": relationship,
    }
    envelope = build_plan_confirmation(
        application_id=application.id,
        version=application.version,
        summary=summary,
        catalog_id=settings.plan_show_catalog_id,
    )
    return (
        application,
        "已提交被保险人信息",
        "被保险人信息已保存，请确认投保方案。",
        envelope,
        "advanced",
    )


def _handle_confirmation(
    session: Session, payload: InsuranceActionRequest, user_id: str, thread_id: str
) -> tuple[InsuranceApplication, str, str, dict[str, Any], Outcome]:
    application = _load_application(session, payload, user_id, thread_id)
    if application.current_step != PLAN_CONFIRMATION:
        raise InsuranceFlowError(
            409,
            "stale_step",
            "请使用最新投保步骤继续",
            current_step=application.current_step,
            version=application.version,
        )
    application.current_step = CONFIRMED
    application.status = CONFIRMED
    application.version = 4
    application.confirmed_at = datetime.now(UTC)
    application.updated_at = datetime.now(UTC)
    envelope = build_completion(
        application_id=application.id, catalog_id=settings.plan_show_catalog_id
    )
    return (
        application,
        "已确认投保方案",
        "方案和基础信息已确认，后续流程待接入。",
        envelope,
        "completed",
    )


def handle_insurance_action(
    session: Session,
    payload: InsuranceActionRequest,
    *,
    user_id: str,
    thread_id: str,
) -> InsuranceActionResponse:
    """在一个数据库事务内执行事件、生成安全消息并记录幂等结果。"""
    _validate_envelope(payload)
    duplicate = _find_duplicate(session, payload, user_id, thread_id)
    if duplicate is not None:
        return duplicate
    try:
        cipher = PIICipher(settings.pii_encryption_key)
    except RuntimeError as exc:
        raise InsuranceFlowError(503, "pii_encryption_unavailable", str(exc)) from exc

    if payload.name == "plan_apply":
        result = _handle_plan_apply(session, payload, user_id, thread_id)
    elif payload.name == "applicant_submit":
        result = _handle_applicant(session, payload, cipher, user_id, thread_id)
    elif payload.name == "insured_submit":
        result = _handle_insured(session, payload, cipher, user_id, thread_id)
    else:
        result = _handle_confirmation(session, payload, user_id, thread_id)
    application, user_summary, assistant_text, envelope, outcome = result
    user_message, assistant_message = _response_messages(
        thread_id=thread_id,
        user_summary=user_summary,
        assistant_text=assistant_text,
        envelope=envelope,
    )
    session.add(user_message)
    session.add(assistant_message)
    session.flush()
    session.add(
        InsuranceEvent(
            event_id=payload.event_id,
            user_id=user_id,
            thread_id=thread_id,
            application_id=application.id,
            event_name=payload.name,
            resulting_step=application.current_step,
            resulting_version=application.version,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
        )
    )
    session.commit()
    session.refresh(user_message)
    session.refresh(assistant_message)
    return InsuranceActionResponse(
        outcome=outcome,
        application_id=application.id,
        current_step=application.current_step,
        version=application.version,
        user_message=_message_read(user_message),
        assistant_message=_message_read(assistant_message),
    )
