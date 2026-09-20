"""消息列表排序稳定性测试：created_at 并列时 user 必须排在 assistant 之前。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models.message import Message
from app.models.thread import Thread


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_list_messages_places_user_before_assistant_on_tied_timestamps():
    engine = _engine()
    thread_id = str(uuid4())
    tied_at = datetime.now(UTC)
    with Session(engine) as session:
        session.add(Thread(id=thread_id, user_id="u1", title="排序测试"))
        session.commit()
        # 复现线上故障的数据形态：成对消息 created_at 完全相同
        for role, content in [
            ("user", "已提交投保人信息"),
            ("assistant", "投保人信息已保存，请填写被保险人信息。"),
        ]:
            references = (
                [
                    {
                        "source_type": "web",
                        "title": "官方公告",
                        "url": "https://example.com/notice",
                        "snippet": "公告摘要",
                        "document_id": None,
                        "chunk_index": None,
                    }
                ]
                if role == "assistant"
                else []
            )
            session.add(
                Message(
                    thread_id=thread_id,
                    role=role,
                    content=content,
                    references=references,
                    created_at=tied_at,
                    updated_at=tied_at,
                )
            )
        session.commit()

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/threads/{thread_id}/messages")
        assert response.status_code == 200
        roles = [message["role"] for message in response.json()]
        assert roles == ["user", "assistant"]
        assert response.json()[0]["references"] == []
        assert response.json()[1]["references"][0]["title"] == "官方公告"
    finally:
        app.dependency_overrides.clear()


def test_list_messages_orders_pairs_by_timestamp_then_user_first():
    """两组并列对按时间先后分段，每组内部 user 在前。"""
    engine = _engine()
    thread_id = str(uuid4())
    base = datetime(2026, 9, 17, 10, 30, 48, tzinfo=UTC)
    with Session(engine) as session:
        session.add(Thread(id=thread_id, user_id="u1", title="排序测试"))
        session.commit()
        for tied_at, contents in [
            (base, ["已提交投保人信息", "投保人信息已保存，请填写被保险人信息。"]),
            (base + timedelta(seconds=18), ["已确认投保方案", "方案和基础信息已确认。"]),
        ]:
            for role, content in zip(["user", "assistant"], contents, strict=True):
                session.add(
                    Message(
                        thread_id=thread_id,
                        role=role,
                        content=content,
                        created_at=tied_at,
                        updated_at=tied_at,
                    )
                )
        session.commit()

    def _override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1")
    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/threads/{thread_id}/messages")
        assert response.status_code == 200
        roles = [message["role"] for message in response.json()]
        assert roles == ["user", "assistant", "user", "assistant"]
    finally:
        app.dependency_overrides.clear()
