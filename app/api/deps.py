from typing import cast

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.core.security import TOKEN_TYPE_ACCESS, decode_token_of_type
from app.models.user import User
from app.services.database import get_session

# OAuth2 密码流，token 从请求头 Authorization: Bearer <token> 获取。
# auto_error=False：缺头时由 get_current_user 抛出统一的中文 401，前端只认状态码。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_db():
    """数据库会话依赖"""
    yield from get_session()


async def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """根据 JWT 获取当前用户，失败一律抛 401（前端据此触发重新登录流程）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录凭据已失效，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录状态已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 只接受 access token；refresh token 不能当访问令牌用
    user_id = decode_token_of_type(token, TOKEN_TYPE_ACCESS)
    if user_id is None:
        raise credentials_exception
    user = cast(User | None, db.get(User, user_id))
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise credentials_exception
    return user
