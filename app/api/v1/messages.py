from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.thread import Thread
from app.models.message import Message
from app.schemas.message import MessageCreate, MessageRead

# 消息路由：嵌套在会话下，接口前缀 /threads/{thread_id}/messages，接口文档标签 messages
router = APIRouter(prefix="/threads/{thread_id}/messages", tags=["messages"])


@router.post("", response_model=MessageRead)
def add_message(
    thread_id: str,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """向指定会话新增一条消息"""
    # 根据会话ID查询会话，校验会话存在性以及归属当前登录用户，防止越权写入
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Thread not found")

    # 构造消息数据库实体，关联会话ID，填充角色与消息内容
    message = Message(
        thread_id=thread_id,
        role=payload.role,
        content=payload.content
    )
    db.add(message)         # 将消息对象加入数据库会话
    db.commit()             # 提交事务持久化数据
    db.refresh(message)     # 刷新实例，回填数据库生成的id等字段
    return message


@router.get("", response_model=list[MessageRead])
def list_messages(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取指定会话下全部消息列表，按创建时间正序返回"""
    # 校验会话存在与归属权，禁止读取他人会话消息
    thread = db.get(Thread, thread_id)
    if not thread or thread.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Thread not found")

    # 查询该会话下所有消息，按照创建时间升序，保证聊天顺序正确
    messages = db.exec(
        select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)
    ).all()
    return messages
