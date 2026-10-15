"""NTF-064 全站公告：预览、定时与撤回（151 号 spec）。

公告是平台对全体用户说的话，而此前它只是一个循环：按下就发、发给谁事后查不到、发错了收不回来，
只能再发一条更正——两条互相矛盾的通知并排躺在每个人的通知中心里。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from .models import Announcement

SCHEDULE_MAX_DAYS = 30
# 锁屏推送标题大约显示这么多字；更长的会被截断（只是提醒，不拦）
PUSH_TITLE_HINT = 20
REVOKED_PREFIX = "【已撤回】"


def audience_query(db: Session, verified_only: bool):
    q = db.query(User).filter(User.is_deleted.is_(False), User.is_banned.is_(False))
    if verified_only:
        q = q.filter(User.is_verified.is_(True))
    return q


def preview(db: Session, title: str, body: str, verified_only: bool) -> dict:
    """发之前说清：会送给多少人、用户看到的样子、有没有要留意的地方。不落库、不发。
    公告这一类用户关不掉（通知偏好里没有它），所以受众人数就是会收到的人数。"""
    audience = audience_query(db, verified_only).count()
    warnings = []
    if len(title) > PUSH_TITLE_HINT:
        warnings.append(f"标题超过 {PUSH_TITLE_HINT} 个字，手机锁屏推送会被截断")
    if not body.strip():
        warnings.append("正文是空的：用户点开只看到标题")
    if not verified_only and any(w in title + body for w in ("资金", "提现", "税", "实名")):
        warnings.append("看起来是资金或合规类公告，是否只发给已实名用户？")
    return {"audience": audience, "verified_only": verified_only, "title": title, "body": body, "warnings": warnings}


def deliver(db: Session, ann: Announcement) -> int:
    from app.modules.notification.service import notify

    count = 0
    for (uid,) in audience_query(db, ann.verified_only).with_entities(User.id):
        notify(db, uid, "announcement", ann.title, ann.body, announcement_id=ann.id)
        count += 1
    ann.status, ann.sent_at, ann.delivered = "sent", utcnow(), count
    return count


def create(db: Session, admin_id: int, title: str, body: str, verified_only: bool,
           scheduled_at: datetime | None) -> Announcement:
    now = utcnow()
    ann = Announcement(title=title, body=body, verified_only=verified_only, created_by=admin_id, created_at=now)
    if scheduled_at is not None:
        if scheduled_at <= now + timedelta(minutes=1):
            raise bad_request("定时发送的时间要晚于现在至少 1 分钟；要马上发就不填时间", "schedule_in_past")
        if scheduled_at > now + timedelta(days=SCHEDULE_MAX_DAYS):
            raise bad_request(f"最多提前 {SCHEDULE_MAX_DAYS} 天定时；更远的请到时候再排", "schedule_too_far")
        ann.status, ann.scheduled_at = "scheduled", scheduled_at
    db.add(ann)
    db.flush()
    if ann.status != "scheduled":
        deliver(db, ann)
    return ann


def send_due(db: Session, now: datetime | None = None) -> list[int]:
    now = now or utcnow()
    due = (db.query(Announcement).filter(Announcement.status == "scheduled", Announcement.scheduled_at <= now)
           .order_by(Announcement.scheduled_at, Announcement.id).with_for_update().all())
    for ann in due:
        deliver(db, ann)
    return [a.id for a in due]


def _get(db: Session, ann_id: int) -> Announcement:
    ann = db.query(Announcement).filter(Announcement.id == ann_id).with_for_update().first()
    if ann is None:
        raise not_found("没有这条公告")
    return ann


def cancel(db: Session, ann_id: int, admin_id: int, reason: str) -> Announcement:
    ann = _get(db, ann_id)
    if ann.status != "scheduled":
        raise conflict("只有还没发出的定时公告能取消；已经发出的请用「撤回」", "announcement_not_scheduled")
    ann.status, ann.closed_by, ann.closed_at, ann.close_reason = "cancelled", admin_id, utcnow(), reason or "取消定时"
    return ann


def revoke(db: Session, ann_id: int, admin_id: int, reason: str) -> tuple[Announcement, int]:
    """把已送达的通知改成「已撤回」并写明理由：用户的通知中心里不会再留着一条错的公告。
    已经推到手机上的推送收不回来——这一点在界面上说清楚。"""
    from app.modules.notification.models import Notification

    ann = _get(db, ann_id)
    if ann.status != "sent":
        raise conflict("只有已发出的公告能撤回；还没发的定时公告请用「取消」", "announcement_not_sent")
    if len(reason.strip()) < 2:
        raise bad_request("撤回要写明理由：用户会看到这句话", "revoke_reason_required")
    note = f"这条公告已撤回：{reason.strip()}"[:500]
    n = 0
    for row in db.query(Notification).filter(Notification.announcement_id == ann.id):
        row.title = (REVOKED_PREFIX + ann.title)[:120]
        row.body = note
        n += 1
    ann.status, ann.closed_by, ann.closed_at, ann.close_reason = "revoked", admin_id, utcnow(), reason.strip()
    return ann, n


def row(a: Announcement) -> dict:
    return {"id": a.id, "title": a.title, "body": a.body, "verified_only": a.verified_only, "status": a.status,
            "scheduled_at": iso(a.scheduled_at), "created_by": a.created_by, "created_at": iso(a.created_at),
            "sent_at": iso(a.sent_at), "delivered": a.delivered, "closed_by": a.closed_by,
            "closed_at": iso(a.closed_at), "close_reason": a.close_reason}
