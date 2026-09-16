"""投保确定性状态机、幂等和消息脱敏测试。"""

from uuid import uuid4

from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.config import settings
from app.models.insurance_application import InsuranceApplication, InsuranceParty
from app.models.message import Message
from app.models.plan_show import PlanShow
from app.schemas.insurance import InsuranceActionRequest
from app.services.insurance.flow import CONFIRMED, InsuranceFlowError, handle_insurance_action

VALID_ID = "11010519491231002X"


def _request(name: str, context: dict, application=None, version=None, event_id=None):
    return InsuranceActionRequest(
        event_id=event_id or str(uuid4()),
        name=name,
        source_surface_id="surface-test",
        application_id=application,
        expected_version=version,
        context=context,
    )


def _person(consent=True):
    return {
        "name": "张三",
        "birth_date": "1949-12-31",
        "occupation": "教师",
        "mobile": "13800138000",
        "id_number": VALID_ID,
        "consent": consent,
    }


def _session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _plan():
    return PlanShow(
        group_code="G0264",
        group_name="测试保险",
        contents="保障",
        order_num=1,
        title_id=1,
        title="寿险",
        title_ord_num=1,
        img=None,
        has_sale="1",
        insur_list=["AYR"],
        is_more_insur=0,
        is_approve=1,
        is_irisk=1,
    )


def test_complete_flow_is_persistent_idempotent_and_redacted(monkeypatch):
    monkeypatch.setattr(settings, "pii_encryption_key", Fernet.generate_key().decode())
    with _session() as session:
        session.add(_plan())
        session.commit()
        first_request = _request("plan_apply", {"group_code": "G0264"})
        first = handle_insurance_action(session, first_request, user_id="u1", thread_id="t1")
        duplicate = handle_insurance_action(session, first_request, user_id="u1", thread_id="t1")
        assert duplicate.outcome == "duplicate"
        assert duplicate.application_id == first.application_id

        applicant = handle_insurance_action(
            session,
            _request(
                "applicant_submit",
                {"form": _person()},
                first.application_id,
                first.version,
            ),
            user_id="u1",
            thread_id="t1",
        )
        insured = handle_insurance_action(
            session,
            _request(
                "insured_submit",
                {"form": {"relationship": "SELF"}},
                first.application_id,
                applicant.version,
            ),
            user_id="u1",
            thread_id="t1",
        )
        completed = handle_insurance_action(
            session,
            _request("plan_confirm", {}, first.application_id, insured.version),
            user_id="u1",
            thread_id="t1",
        )

        application = session.get(InsuranceApplication, first.application_id)
        parties = session.exec(
            select(InsuranceParty).where(InsuranceParty.application_id == first.application_id)
        ).all()
        messages = session.exec(select(Message).where(Message.thread_id == "t1")).all()
        assert completed.outcome == "completed"
        assert application is not None and application.status == CONFIRMED
        assert len(parties) == 2
        assert parties[0].encrypted_payload == parties[1].encrypted_payload
        persisted_text = "\n".join(message.content or "" for message in messages)
        assert "张三" not in persisted_text
        assert "13800138000" not in persisted_text
        assert VALID_ID not in persisted_text
        assert "张*" in insured.assistant_message.content


def test_validation_error_does_not_persist_plaintext(monkeypatch):
    monkeypatch.setattr(settings, "pii_encryption_key", Fernet.generate_key().decode())
    with _session() as session:
        session.add(_plan())
        session.commit()
        first = handle_insurance_action(
            session,
            _request("plan_apply", {"group_code": "G0264"}),
            user_id="u1",
            thread_id="t1",
        )
        try:
            handle_insurance_action(
                session,
                _request(
                    "applicant_submit",
                    {"form": _person(consent=False)},
                    first.application_id,
                    first.version,
                ),
                user_id="u1",
                thread_id="t1",
            )
        except InsuranceFlowError as exc:
            assert exc.status_code == 422
            assert exc.detail["field_errors"] == {
                "consent": "请阅读并同意个人信息处理授权及投保须知"
            }
        else:
            raise AssertionError("未勾选授权时必须拒绝提交")
        persisted_text = "\n".join(
            message.content or "" for message in session.exec(select(Message)).all()
        )
        assert "张三" not in persisted_text


def test_missing_encryption_key_disables_flow_without_affecting_other_services(monkeypatch):
    monkeypatch.setattr(settings, "pii_encryption_key", None)
    with _session() as session:
        session.add(_plan())
        session.commit()
        try:
            handle_insurance_action(
                session,
                _request("plan_apply", {"group_code": "G0264"}),
                user_id="u1",
                thread_id="t1",
            )
        except InsuranceFlowError as exc:
            assert exc.status_code == 503
            assert exc.detail["code"] == "pii_encryption_unavailable"
        else:
            raise AssertionError("缺少独立加密密钥时必须禁用投保流程")


def test_stale_version_cannot_overwrite_completed_step(monkeypatch):
    monkeypatch.setattr(settings, "pii_encryption_key", Fernet.generate_key().decode())
    with _session() as session:
        session.add(_plan())
        session.commit()
        first = handle_insurance_action(
            session,
            _request("plan_apply", {"group_code": "G0264"}),
            user_id="u1",
            thread_id="t1",
        )
        handle_insurance_action(
            session,
            _request("applicant_submit", {"form": _person()}, first.application_id, first.version),
            user_id="u1",
            thread_id="t1",
        )
        try:
            handle_insurance_action(
                session,
                _request(
                    "applicant_submit", {"form": _person()}, first.application_id, first.version
                ),
                user_id="u1",
                thread_id="t1",
            )
        except InsuranceFlowError as exc:
            assert exc.status_code == 409
            assert exc.detail["code"] == "stale_step"
            assert exc.detail["version"] == 2
        else:
            raise AssertionError("历史表单不得覆盖已完成步骤")
