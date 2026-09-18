import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# JWT payload 中的令牌类型声明，用于阻断 refresh token 冒充 access token（反之亦然）
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def create_token(
    subject: str | Any, token_type: str, expires_delta: timedelta | None = None
) -> str:
    """生成指定类型的 JWT，payload 中写入 exp、sub、type、jti 声明"""
    if expires_delta is None:
        if token_type == TOKEN_TYPE_REFRESH:
            expires_delta = timedelta(days=settings.refresh_token_expire_days)
        else:
            expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expire = datetime.now(UTC) + expires_delta
    # jti 保证同一秒内多次签发内容也不同（exp 只有秒级精度），避免令牌哈希碰撞
    to_encode = {"exp": expire, "sub": str(subject), "type": token_type, "jti": str(uuid4())}
    encoded_jwt: str = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """生成 JWT 访问令牌"""
    return create_token(subject, TOKEN_TYPE_ACCESS, expires_delta)


def create_refresh_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    """生成 JWT 刷新令牌，有效期独立于访问令牌"""
    return create_token(subject, TOKEN_TYPE_REFRESH, expires_delta)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码，使用 bcrypt 原生 API"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    """生成密码哈希（超过 72 字节会抛出异常，需要提前处理）"""
    # bcrypt 要求密码不超过 72 字节；这里不做静默截断，由调用方确保长度
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def decode_token(token: str) -> dict[str, Any] | None:
    """解码 JWT，返回完整 payload；签名错误或过期返回 None"""
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
        return None


def decode_token_of_type(token: str, token_type: str) -> str | None:
    """解码指定类型的令牌并返回 subject（用户ID）。

    令牌类型不匹配（如拿 refresh token 当 access token 用）或签名/过期失败返回 None；
    兼容历史签发的无 type 声明的令牌，视作 access token。
    """
    payload = decode_token(token)
    if payload is None:
        return None
    claimed_type = payload.get("type", TOKEN_TYPE_ACCESS)
    if claimed_type != token_type:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def decode_access_token(token: str) -> str | None:
    """解码访问令牌，返回 subject（用户ID）；失败或类型不符返回 None"""
    return decode_token_of_type(token, TOKEN_TYPE_ACCESS)


def decode_refresh_token(token: str) -> str | None:
    """解码刷新令牌，返回 subject（用户ID）；失败或类型不符返回 None"""
    return decode_token_of_type(token, TOKEN_TYPE_REFRESH)


def hash_token(token: str) -> str:
    """刷新令牌入库前做 SHA-256 摘要，避免明文落库后被拖库直接冒用"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
