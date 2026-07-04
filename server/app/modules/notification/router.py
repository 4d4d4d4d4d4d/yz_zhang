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


@router.get("/prefs")
def get_prefs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.modules.support.models import NotificationPref

    rows = db.query(NotificationPref).filter(NotificationPref.user_id == user.id).all()
    prefs = {"task": True, "system": True, "interaction": True}
    for r in rows:
        prefs[r.category] = r.enabled
    return prefs


@router.put("/prefs")
def set_pref(
    category: str, enabled: bool, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """NTF-003：funds 资金必达类不可关闭。"""
    from app.core.errors import bad_request
    from app.modules.support.models import NotificationPref

    if category == "funds":
        raise bad_request("资金类通知为必达通知，不可关闭", "funds_mandatory")
    if category not in ("task", "system", "interaction"):
        raise bad_request("非法通知分类", "invalid_category")
    row = (
        db.query(NotificationPref)
        .filter(NotificationPref.user_id == user.id, NotificationPref.category == category)
        .first()
    )
    if not row:
        row = NotificationPref(user_id=user.id, category=category)
    row.enabled = enabled
    db.add(row)
    return {"category": category, "enabled": enabled}


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
