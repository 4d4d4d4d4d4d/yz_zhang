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


class QuoteCardIn(BaseModel):
    """IM-009 报价卡：结构化消息，可直达报名。"""

    task_id: int
    price_cents: int = Field(gt=0)
    note: str = Field(default="", max_length=200)


def _dump_conv(c: Conversation) -> dict:
    return {"id": c.id, "kind": c.kind, "task_id": c.task_id, "participants": c.participants}


def _read_cursor(db: Session, conv_id: int, user_id: int) -> int:
    from .models import ConversationRead

    row = (
        db.query(ConversationRead)
        .filter(ConversationRead.conversation_id == conv_id,
                ConversationRead.user_id == user_id)
        .first()
    )
    return (row.last_read_message_id or 0) if row else 0


@router.get("/conversations")
def my_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IM-010 会话列表附未读数与最后一条消息预览（聊天列表标配）。"""
    from sqlalchemy import func

    rows = [
        c for c in db.query(Conversation).order_by(Conversation.id.desc()).all()
        if user.id in c.participants
    ]
    out = []
    for c in rows:
        cursor = _read_cursor(db, c.id, user.id)
        unread = (
            db.query(func.count(Message.id))
            .filter(Message.conversation_id == c.id, Message.id > cursor,
                    Message.sender_id != user.id)  # 自己发的不算未读
            .scalar()
        )
        last = (
            db.query(Message).filter(Message.conversation_id == c.id)
            .order_by(Message.id.desc()).first()
        )
        out.append({
            **_dump_conv(c),
            "unread_count": int(unread),
            "last_message": None if not last else {
                "id": last.id, "sender_id": last.sender_id, "kind": last.kind,
                "content": "[消息已撤回]" if last.recalled else last.content[:100],
                "created_at": last.created_at.isoformat(),
            },
        })
    # 有未读的会话优先，其次按最后消息时间倒序（业界聊天列表排序）
    out.sort(key=lambda x: (x["unread_count"] == 0,
                            -(x["last_message"]["id"] if x["last_message"] else 0)))
    return out


@router.get("/conversations/unread-count")
def im_unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IM-010 全局未读消息数（聊天 Tab 红点）。"""
    from sqlalchemy import func

    total = 0
    for c in db.query(Conversation).all():
        if user.id not in c.participants:
            continue
        cursor = _read_cursor(db, c.id, user.id)
        total += int(
            db.query(func.count(Message.id))
            .filter(Message.conversation_id == c.id, Message.id > cursor,
                    Message.sender_id != user.id)
            .scalar()
        )
    return {"unread": total}


@router.post("/conversations/{conv_id}/read")
def mark_conversation_read(
    conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """IM-010 标记会话已读（推进已读位点到最新一条）。"""
    from app.modules.account.models import utcnow

    from .models import ConversationRead

    _get_conv(db, conv_id, user)  # 复用参与者鉴权
    last = (
        db.query(Message).filter(Message.conversation_id == conv_id)
        .order_by(Message.id.desc()).first()
    )
    last_id = last.id if last else 0
    row = (
        db.query(ConversationRead)
        .filter(ConversationRead.conversation_id == conv_id,
                ConversationRead.user_id == user.id)
        .first()
    )
    if not row:
        row = ConversationRead(conversation_id=conv_id, user_id=user.id, last_read_message_id=0)
    row.last_read_message_id = max(row.last_read_message_id or 0, last_id)
    row.updated_at = utcnow()
    db.add(row)
    return {"conversation_id": conv_id, "last_read_message_id": row.last_read_message_id}


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


@router.post("/conversations/{conv_id}/quote-cards", status_code=201)
def send_quote_card(
    conv_id: int, body: QuoteCardIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """IM-009 发送报价卡（结构化 JSON 内容，前端渲染为卡片）。"""
    import json

    conv = _get_conv(db, conv_id, user)
    payload = json.dumps(
        {"task_id": body.task_id, "price_cents": body.price_cents, "note": body.note},
        ensure_ascii=False,
    )
    msg = service.send(db, conv, user.id, payload, kind="quote")
    return {"id": msg.id, "kind": "quote"}


@router.get("/conversations/{conv_id}/messages")
def list_messages(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = _get_conv(db, conv_id, user)
    rows = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.id).all()
    return [
        {"id": m.id, "sender_id": m.sender_id, "kind": m.kind,
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
