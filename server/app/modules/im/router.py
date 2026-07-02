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
        {"id": m.id, "sender_id": m.sender_id, "content": m.content,
         "risk_flagged": m.risk_flagged, "created_at": m.created_at.isoformat()}
        for m in rows
    ]
