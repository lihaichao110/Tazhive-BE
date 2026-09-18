"""登录令牌对与刷新轮换集成测试，对应 401 语义与令牌对契约的验收清单。

只覆盖 get_db 依赖（内存 SQLite），认证链路走真实 JWT + refresh_tokens 表。
每个用例前重置限流器，避免登录接口 5/minute 限流误伤测试。
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.deps import get_db
from app.core.limiter import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
)
from app.main import app
from app.models.user import User


def _engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _add_user(engine, *, password: str = "password123") -> User:
    user = User(
        username=f"user-{uuid4()}",
        email=f"{uuid4()}@example.com",
        hashed_password=get_password_hash(password),
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
def auth_client(db_engine):
    limiter.reset()

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


def _login(client: TestClient, username: str, password: str = "password123"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


# ---------- 改动1：业务接口 401 语义 ----------


def test_threads_without_token_returns_401(auth_client):
    response = auth_client.get("/api/v1/threads")

    assert response.status_code == 401
    assert response.json()["detail"]


def test_threads_with_forged_token_returns_401(auth_client):
    response = auth_client.get("/api/v1/threads", headers=_auth_header("forged-token"))

    assert response.status_code == 401
    assert response.json()["detail"]
    assert response.headers["www-authenticate"] == "Bearer"


def test_threads_with_expired_token_returns_401(auth_client, db_engine):
    user = _add_user(db_engine)
    expired = create_access_token(user.id, expires_delta=timedelta(seconds=-1))
    response = auth_client.get("/api/v1/threads", headers=_auth_header(expired))

    assert response.status_code == 401
    assert response.json()["detail"]


def test_threads_with_valid_token_returns_200(auth_client, db_engine):
    user = _add_user(db_engine)
    response = auth_client.get(
        "/api/v1/threads", headers=_auth_header(create_access_token(user.id))
    )

    assert response.status_code == 200
    assert response.json() == []


def test_threads_rejects_refresh_token_as_access_token(auth_client, db_engine):
    user = _add_user(db_engine)
    refresh = create_refresh_token(user.id)
    response = auth_client.get("/api/v1/threads", headers=_auth_header(refresh))

    assert response.status_code == 401


# ---------- 改动2：登录返回令牌对 ----------


def test_login_returns_non_empty_token_pair(auth_client, db_engine):
    user = _add_user(db_engine)
    response = _login(auth_client, user.username)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


def test_login_wrong_password_returns_401_with_detail(auth_client, db_engine):
    user = _add_user(db_engine)
    response = _login(auth_client, user.username, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"]


# ---------- 改动3：刷新轮换 ----------


def test_refresh_rotates_pair_without_auth_header(auth_client, db_engine):
    user = _add_user(db_engine)
    old_tokens = _login(auth_client, user.username).json()
    response = auth_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}
    )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    # 轮换契约：新旧令牌对完全不同
    assert new_tokens["access_token"] != old_tokens["access_token"]
    assert new_tokens["refresh_token"] != old_tokens["refresh_token"]


def test_old_refresh_token_reuse_returns_401(auth_client, db_engine):
    user = _add_user(db_engine)
    old_tokens = _login(auth_client, user.username).json()
    auth_client.post("/api/v1/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]})

    response = auth_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}
    )

    assert response.status_code == 401


def test_new_access_token_works_on_threads(auth_client, db_engine):
    user = _add_user(db_engine)
    old_tokens = _login(auth_client, user.username).json()
    new_tokens = auth_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_tokens["refresh_token"]}
    ).json()

    response = auth_client.get("/api/v1/threads", headers=_auth_header(new_tokens["access_token"]))

    assert response.status_code == 200
    assert response.json() == []


def test_expired_refresh_token_returns_401(auth_client, db_engine):
    user = _add_user(db_engine)
    expired = create_refresh_token(user.id, expires_delta=timedelta(seconds=-1))
    response = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": expired})

    assert response.status_code == 401


def test_refresh_with_malformed_token_returns_401(auth_client):
    response = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["detail"]


def test_refresh_with_access_token_returns_401(auth_client, db_engine):
    user = _add_user(db_engine)
    access = create_access_token(user.id)
    response = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": access})

    assert response.status_code == 401


def test_refresh_without_body_token_returns_422(auth_client):
    # 缺少 refresh_token 字段属于请求格式错误，FastAPI 校验层返回 422
    response = auth_client.post("/api/v1/auth/refresh", json={})

    assert response.status_code == 422


def test_refresh_for_unknown_user_returns_401(auth_client, db_engine):
    # 令牌签名有效但用户不存在（如被删除），同样视为会话不可恢复
    ghost = create_refresh_token(str(uuid4()))
    response = auth_client.post("/api/v1/auth/refresh", json={"refresh_token": ghost})

    assert response.status_code == 401
