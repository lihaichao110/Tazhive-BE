from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_token,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenResponse


def issue_token_pair(db: Session, user: User) -> TokenResponse:
    """为用户签发全新的访问+刷新令牌对，并把刷新令牌摘要落库追踪"""
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        # 数据库 DateTime 列不带时区，统一存 naive UTC
        expires_at=(datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)).replace(
            tzinfo=None
        ),
    )
    db.add(record)
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


def rotate_refresh_token(db: Session, raw_refresh_token: str) -> TokenResponse | None:
    """校验并轮换刷新令牌：旧令牌作废，返回全新令牌对。

    令牌无效/过期/已作废/用户不可用返回 None，由路由层统一转成 401。
    """
    user_id = decode_refresh_token(raw_refresh_token)
    if user_id is None:
        return None

    record = db.exec(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_refresh_token))
    ).first()
    # 库中无记录（如不存在的令牌）或已被轮换作废，按单次有效处理
    if record is None or record.revoked:
        return None
    # 数据库侧过期兜底，与 JWT exp 声明双保险；库里存的是 naive UTC
    if record.expires_at <= datetime.now(UTC).replace(tzinfo=None):
        return None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None

    record.revoked = True
    db.add(record)
    return issue_token_pair(db, user)
