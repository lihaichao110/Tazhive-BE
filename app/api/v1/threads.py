from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.thread import Thread
from app.schemas.thread import ThreadCreate, ThreadRead

# 会话路由实例，接口统一前缀 /threads，接口文档标签 threads
router = APIRouter(prefix="/threads", tags=["threads"])


@router.post("", response_model=ThreadRead)
def create_thread(
    payload: ThreadCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建新会话"""
    # 构造数据库实体，绑定当前登录用户ID与传入标题
    thread = Thread(user_id=current_user.id, title=payload.title)
    db.add(thread)          # 加入会话到数据库session
    db.commit()             # 提交事务持久化数据
    db.refresh(thread)      # 刷新实例，回填数据库生成的id、时间等字段
    return thread


@router.get("", response_model=list[ThreadRead])
def list_threads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前用户的全部会话列表"""
    # 查询条件：只查询属于当前登录用户的会话
    threads = db.exec(
        select(Thread).where(Thread.user_id == current_user.id)
    ).all()
    return threads


@router.get("/{thread_id}", response_model=ThreadRead)
def get_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """根据会话ID获取单条会话详情"""
    # 通过主键查询会话记录
    thread = db.get(Thread, thread_id)
    # 校验：记录不存在 或者 会话不属于当前用户，统一返回404，避免资源越权探测
    if not thread or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.delete("/{thread_id}", status_code=204)
def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除指定会话，204 NoContent无返回体"""
    thread = db.get(Thread, thread_id)
    # 校验会话存在性 + 归属权校验，防止越权删除他人会话
    if not thread or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Thread not found")

    db.delete(thread)   # session标记删除对象
    db.commit()         # 提交事务完成数据库删除
