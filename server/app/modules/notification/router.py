from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import not_found
from app.modules.account.models import User

from .models import Notification

router = APIRouter(prefix="/notifications", tags=["notification"])


@router.get("")
def list_notifications(
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.id.desc()).limit(100).all()
    return [
        {"id": n.id, "category": n.category, "title": n.title, "body": n.body,
         "is_read": n.is_read, "created_at": n.created_at.isoformat()}
        for n in rows
    ]


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != user.id:
        raise not_found("通知不存在")
    n.is_read = True
    db.add(n)
    return {"ok": True}
