"""GET /api/v1/auth/verify 集成测试：应用启动时的登录会话校验（ADR-0003）。

只覆盖 get_db 依赖（内存 SQLite），认证依赖 get_current_user 走真实 JWT 链路。
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.user import User


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _add_user(engine, *, is_active: bool = True) -> User:
    user = User(
        username=f"user-{uuid4()}",
        email=f"{uuid4()}@example.com",
        hashed_password=get_password_hash("password123"),
        is_active=is_active,
    )
    with Session(engine) as session:
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def db_engine():
    return _engine()


@pytest.fixture
def verify_client(db_engine):
    def _override_db():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_verify_returns_204_with_no_store_for_valid_token(verify_client, db_engine):
    user = _add_user(db_engine)
    response = verify_client.get(
        "/api/v1/auth/verify", headers=_auth_header(create_access_token(user.id))
    )

    assert response.status_code == 204
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store"


def test_verify_rejects_missing_token(verify_client):
    response = verify_client.get("/api/v1/auth/verify")

    assert response.status_code == 401


def test_verify_rejects_malformed_token(verify_client):
    response = verify_client.get("/api/v1/auth/verify", headers=_auth_header("not-a-jwt"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_verify_rejects_token_of_unknown_user(verify_client):
    token = create_access_token(str(uuid4()))
    response = verify_client.get("/api/v1/auth/verify", headers=_auth_header(token))

    assert response.status_code == 401


def test_verify_rejects_expired_token(verify_client, db_engine):
    user = _add_user(db_engine)
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-1))
    response = verify_client.get("/api/v1/auth/verify", headers=_auth_header(token))

    assert response.status_code == 401


def test_verify_rejects_inactive_user(verify_client, db_engine):
    user = _add_user(db_engine, is_active=False)
    response = verify_client.get(
        "/api/v1/auth/verify", headers=_auth_header(create_access_token(user.id))
    )

    assert response.status_code == 401
