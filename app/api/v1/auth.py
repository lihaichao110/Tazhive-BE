from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.limiter import limiter
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import TokenResponse, UserLogin, UserRegister

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

    # 生成令牌
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


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

    # 生成令牌
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get(
    "/verify",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"description": "令牌无效、已过期或账号不可用"}},
)
def verify_session(response: Response, current_user: User = Depends(get_current_user)) -> None:
    """校验登录会话：令牌有效返回 204，无效/过期/账号不可用由认证依赖返回 401。"""
    # 禁止缓存登录态校验结论，避免中间层复用旧结果
    response.headers["Cache-Control"] = "no-store"
