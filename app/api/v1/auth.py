from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.limiter import limiter
from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenResponse, UserLogin, UserRegister
from app.services.auth import issue_token_pair, rotate_refresh_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: UserRegister, db: Session = Depends(get_db)):
    # slowapi 通过 request 获取客户端信息并执行限流。
    # 检查用户名或邮箱是否已存在
    existing = db.exec(
        select(User).where((User.username == payload.username) | (User.email == payload.email))
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名或电子邮件已存在")

    # 创建新用户
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 注册成功直接登录，下发访问+刷新令牌对
    return issue_token_pair(db, user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: UserLogin, db: Session = Depends(get_db)):
    # slowapi 通过 request 获取客户端信息并执行限流。
    # 查找用户
    user: User | None = db.exec(select(User).where(User.username == payload.username)).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码不正确",
        )

    # 下发访问+刷新令牌对；前端凭 refresh_token 自动续签
    return issue_token_pair(db, user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={401: {"description": "刷新令牌缺失、无效、过期或已作废"}},
)
@limiter.limit("30/minute")
def refresh_tokens(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    """用刷新令牌换取全新令牌对（轮换，旧令牌立即作废）。

    前端不带 Authorization 头调用；任何失败一律 401，由前端判定会话不可恢复。
    """
    token_pair = rotate_refresh_token(db, payload.refresh_token)
    if token_pair is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期，请重新登录",
        )
    return token_pair


@router.get(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "令牌无效、已过期或账号不可用"}},
)
def verify_session(response: Response, current_user: User = Depends(get_current_user)) -> None:
    """校验登录会话：令牌有效返回 204，无效/过期/账号不可用由认证依赖返回 401。"""
    # 禁止缓存登录态校验结论，避免中间层复用旧结果
    response.headers["Cache-Control"] = "no-store"
