from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_and_verify():
    password = "secret123"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_token_roundtrip():
    token = create_access_token("user123")
    user_id = decode_access_token(token)
    assert user_id == "user123"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user123")
    assert decode_refresh_token(token) == "user123"


def test_refresh_token_rejected_as_access_token():
    token = create_refresh_token("user123")
    assert decode_access_token(token) is None


def test_access_token_rejected_as_refresh_token():
    token = create_access_token("user123")
    assert decode_refresh_token(token) is None


def test_expired_token_rejected():
    token = create_access_token("user123", expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None
    assert decode_refresh_token(token) is None


def test_legacy_token_without_type_claim_treated_as_access():
    # 历史版本签发的令牌没有 type 声明，兼容视作 access token
    legacy = jwt.encode(
        {"sub": "user123", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert decode_access_token(legacy) == "user123"
    assert decode_refresh_token(legacy) is None
    assert decode_token(legacy)["sub"] == "user123"
