from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User

from . import service
from .models import Conversation, Message

router = APIRouter(tags=["im"])


class DirectIn(BaseModel):
    user_id: int


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


def _dump_conv(c: Conversation) -> dict:
    return {"id": c.id, "kind": c.kind, "task_id": c.task_id, "participants": c.participants}


@router.get("/conversations")
def my_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Conversation).order_by(Conversation.id.desc()).all()
    return [_dump_conv(c) for c in rows if user.id in c.participants]


@router.post("/conversations/direct")
def open_direct(body: DirectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.user_id == user.id:
        raise forbidden("不能和自己聊天")
    if not db.get(User, body.user_id):
        raise not_found("用户不存在")
    from app.modules.account.service import is_blocked_between

    if is_blocked_between(db, user.id, body.user_id):  # ACC-033
        raise forbidden("对方不可用", "blocked")
    return _dump_conv(service.get_or_create_direct(db, user.id, body.user_id))


def _get_conv(db: Session, conv_id: int, user: User) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise not_found("会话不存在")
    if user.id not in conv.participants and not user.is_admin:
        raise forbidden()
    return conv


@router.post("/conversations/{conv_id}/messages", status_code=201)
def send_message(
    conv_id: int, body: MessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    conv = _get_conv(db, conv_id, user)
    if conv.kind == "direct":
        from app.modules.account.service import is_blocked_between

        other = next((p for p in conv.participants if p != user.id), None)
        if other and is_blocked_between(db, user.id, other):
            raise forbidden("对方不可用", "blocked")
    msg = service.send(db, conv, user.id, body.content)
    return {
        "id": msg.id,
        "risk_flagged": msg.risk_flagged,
        # IM-006 命中风控时给发送方提示（教育型而非拦截型）
        "warning": "请勿引导站外交易，脱离平台交易将失去资金保障" if msg.risk_flagged else None,
    }


@router.get("/conversations/{conv_id}/messages")
def list_messages(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = _get_conv(db, conv_id, user)
    rows = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.id).all()
    return [
        {"id": m.id, "sender_id": m.sender_id,
         # IM-004 撤回消息展示层隐藏（管理员仲裁时可见审计副本）
         "content": "[消息已撤回]" if m.recalled and not user.is_admin else m.content,
         "recalled": m.recalled,
         "risk_flagged": m.risk_flagged, "created_at": m.created_at.isoformat()}
        for m in rows
    ]


@router.post("/messages/{message_id}/recall")
def recall_message(message_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IM-004：发送者 2 分钟内可撤回；任务会话保留后台审计副本。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow

    msg = db.get(Message, message_id)
    if not msg:
        raise not_found("消息不存在")
    if msg.sender_id != user.id:
        raise forbidden("仅发送者可撤回")
    if msg.recalled:
        raise forbidden("已撤回", "already_recalled")
    if utcnow() - msg.created_at > timedelta(minutes=2):
        raise forbidden("超过 2 分钟不可撤回", "recall_window_expired")
    msg.recalled = True
    db.add(msg)
    return {"ok": True}
