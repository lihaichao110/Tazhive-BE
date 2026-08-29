from datetime import datetime, timedelta, timezone
from typing import Any, Union
from jose import jwt, JWTError
import bcrypt
from app.core.config import settings

def create_access_token(subject: Union[str, Any], expires_delta: timedelta | None = None) -> str:
    """生成 JWT 访问令牌"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码，使用 bcrypt 原生 API"""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except (ValueError, TypeError):
        return False

def get_password_hash(password: str) -> str:
    """生成密码哈希（超过 72 字节会抛出异常，需要提前处理）"""
    # bcrypt 要求密码不超过 72 字节；这里不做静默截断，由调用方确保长度
    if len(password.encode('utf-8')) > 72:
        raise ValueError("Password must be at most 72 bytes")
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def decode_access_token(token: str) -> str | None:
    """解码令牌，返回 subject（用户ID）；失败返回 None"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None