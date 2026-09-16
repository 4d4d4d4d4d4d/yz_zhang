from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
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
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notification).filter(Notification.user_id == user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.id.desc()).offset(offset).limit(limit).all()
    return [
        {"id": n.id, "category": n.category, "title": n.title, "body": n.body,
         "is_read": n.is_read, "created_at": n.created_at.isoformat()}
        for n in rows
    ]


@router.get("/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """NTF-005 未读徽章计数（应用红点标准能力）。"""
    count = (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .scalar()
    )
    return {"unread": int(count)}


@router.post("/read-all")
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """NTF-005 一键全部已读。"""
    marked = (
        db.query(Notification)
        .filter(Notification.user_id == user.id, Notification.is_read.is_(False))
        .update({"is_read": True})
    )
    return {"marked": int(marked)}


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

# ---------- NTF-002 设备令牌 ----------
class DeviceIn(BaseModel):
    token: str = Field(min_length=8, max_length=255)
    platform: str = Field(default="ios", pattern="^(ios|android|web)$")


@router.put("/devices")
def register_device(
    body: DeviceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """NTF-002 注册推送令牌。

    令牌是主键，所以重复注册是**幂等**的——App 每次启动都会调这个接口，
    攒出重复行的后果是同一条通知推四遍。
    """
    from app.modules.account.models import utcnow

    from .models_device import DeviceToken

    row = db.get(DeviceToken, body.token)
    if row:
        # 换账号登录同一台设备：令牌要改归属，否则新用户的通知会推给旧用户
        row.user_id, row.platform = user.id, body.platform
        row.revoked = False
        row.last_seen_at = utcnow()
    else:
        row = DeviceToken(token=body.token, user_id=user.id, platform=body.platform)
    db.add(row)
    return {"registered": True, "platform": row.platform}


@router.delete("/devices/{token}")
def unregister_device(
    token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """退出登录/关闭推送时注销令牌。幂等：删一个不存在的也返回 ok。"""
    from .models_device import DeviceToken

    row = db.get(DeviceToken, token)
    if row and row.user_id == user.id:
        row.revoked = True
        db.add(row)
    return {"ok": True}


@router.get("/devices")
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models_device import DeviceToken

    rows = db.query(DeviceToken).filter(
        DeviceToken.user_id == user.id, DeviceToken.revoked.is_(False)).all()
    return [{"platform": r.platform, "token": r.token[:6] + "…",
             "last_seen_at": r.last_seen_at.isoformat()} for r in rows]
