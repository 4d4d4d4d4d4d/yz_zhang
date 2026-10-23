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


AUDIENCES = {"all": "全体用户", "publishers": "近 180 天发过单的人", "workers": "近 180 天报过名接单的人"}
ACTIVE_DAYS = 180


def merge_categories(category: str = "", categories: list[str] | None = None) -> list[str]:
    """NTF-070（246 号 spec）主类目 + 「也发给」的类目，去重保序。"""
    return list(dict.fromkeys([c for c in [category, *(categories or [])] if c]))


def audience_query(db: Session, verified_only: bool, city: str = "", audience: str = "all", category: str = "",
                   categories: list[str] | None = None):
    """NTF-066（159 号 spec）定向：仅已实名、城市、人群（发单的 / 接单的）可以叠加。
    NTF-068（238 号 spec）再叠加类目：近 180 天在这个类目发过单（发单的）/ 报过名（接单的）/ 两者之一（全体）。"""
    q = db.query(User).filter(User.is_deleted.is_(False), User.is_banned.is_(False))
    if verified_only:
        q = q.filter(User.is_verified.is_(True))
    if city:
        q = q.filter(User.city == city)
    cats = merge_categories(category, categories)
    if cats:
        from sqlalchemy import or_

        from app.modules.task.models import Application, Task

        since = utcnow() - timedelta(days=ACTIVE_DAYS)
        # NTF-070（246 号 spec）几个类目取并集
        pub = db.query(Task.creator_id).filter(Task.category.in_(cats), Task.created_at >= since)
        app_ = (db.query(Application.applicant_id).join(Task, Task.id == Application.task_id)
                .filter(Task.category.in_(cats), Application.created_at >= since))
        if audience == "publishers":
            q = q.filter(User.id.in_(pub))
        elif audience == "workers":
            q = q.filter(User.id.in_(app_))
        else:
            q = q.filter(or_(User.id.in_(pub), User.id.in_(app_)))
        return q
    if audience != "all":
        from app.modules.task.models import Application, Task

        since = utcnow() - timedelta(days=ACTIVE_DAYS)
        if audience == "publishers":
            ids = db.query(Task.creator_id).filter(Task.created_at >= since)
        else:
            ids = db.query(Application.applicant_id).filter(Application.created_at >= since)
        q = q.filter(User.id.in_(ids))
    return q


def check_audience(audience: str) -> None:
    if audience not in AUDIENCES:
        raise bad_request(f"人群只能是：{'、'.join(f'{k}（{v}）' for k, v in AUDIENCES.items())}", "bad_audience")


def check_category(db: Session, category: str) -> None:
    """NTF-068 类目要是平台上有的（写错一个字就一个人都发不到）。"""
    if not category:
        return
    from app.modules.task.models import Category

    if db.query(Category).filter(Category.name == category).first() is None:
        raise bad_request(f"没有「{category}」这个类目：请从类目列表里选", "announcement_bad_category")


def preview(db: Session, title: str, body: str, verified_only: bool, city: str = "", audience: str = "all",
            category: str = "", categories: list[str] | None = None) -> dict:
    """发之前说清：会送给多少人、用户看到的样子、有没有要留意的地方。不落库、不发。
    公告这一类用户关不掉（通知偏好里没有它），所以受众人数就是会收到的人数。"""
    check_audience(audience)
    cats = merge_categories(category, categories)
    for c in cats:
        check_category(db, c)
    n = audience_query(db, verified_only, city, audience, category, categories).count()
    warnings = []
    if n == 0:
        warnings.append("按这个条件一个人都发不到：检查城市名是否写对"
                        + ("，或者这个类目近 180 天没人发单 / 报名" if cats else ""))
    if len(title) > PUSH_TITLE_HINT:
        warnings.append(f"标题超过 {PUSH_TITLE_HINT} 个字，手机锁屏推送会被截断")
    if not body.strip():
        warnings.append("正文是空的：用户点开只看到标题")
    if not verified_only and any(w in title + body for w in ("资金", "提现", "税", "实名")):
        warnings.append("看起来是资金或合规类公告，是否只发给已实名用户？")
    return {"audience": n, "verified_only": verified_only, "city": city, "audience_kind": audience, "title": title, "body": body,
            "warnings": warnings, "category": category,
            # NTF-070 选了不止一个类目才带（只选一个时响应与 V265 一样）
            **({"categories": cats} if len(cats) > 1 else {})}


def deliver(db: Session, ann: Announcement) -> int:
    from app.modules.notification.service import notify

    count = 0
    for (uid,) in audience_query(db, ann.verified_only, ann.city or "", ann.audience or "all",
                                 ann.category or "", list(ann.categories or [])).with_entities(User.id):
        notify(db, uid, "announcement", ann.title, ann.body, announcement_id=ann.id)
        count += 1
    ann.status, ann.sent_at, ann.delivered = "sent", utcnow(), count
    return count


def create(db: Session, admin_id: int, title: str, body: str, verified_only: bool,
           scheduled_at: datetime | None, city: str = "", audience: str = "all", category: str = "",
           categories: list[str] | None = None) -> Announcement:
    check_audience(audience)
    cats = merge_categories(category, categories)
    for c in cats:
        check_category(db, c)
    now = utcnow()
    ann = Announcement(title=title, body=body, verified_only=verified_only, created_by=admin_id, created_at=now,
                       city=city, audience=audience, category=category, categories=cats if len(cats) > 1 else [])
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


def read_counts(db: Session, ids: list[int]) -> dict[int, int]:
    """NTF-067 每条公告有多少人点开过（通知的已读位）。"""
    from sqlalchemy import func

    from app.modules.notification.models import Notification

    if not ids:
        return {}
    rows = (db.query(Notification.announcement_id, func.count(Notification.id))
            .filter(Notification.announcement_id.in_(ids), Notification.is_read.is_(True))
            .group_by(Notification.announcement_id).all())
    return {k: int(v) for k, v in rows}


def read_by_category(db: Session, ann: Announcement) -> dict:
    """NTF-071（252 号 spec）多类目公告按类目拆开看阅读率：每个类目里收到了几个人、点开了几个。
    类目归属按**发出时**算（发出前 180 天在这类发过单 / 报过名），与圈人时同一口径；一个人可以同时属于几个类目。"""
    from app.modules.notification.models import Notification
    from app.modules.task.models import Application, Task

    cats = list(ann.categories or []) or ([ann.category] if ann.category else [])
    base = {"announcement_id": ann.id, "categories": []}
    if not cats or ann.sent_at is None:
        return {**base, "overlap": 0, "note": "这条公告没有按类目定向，或还没发出"}
    got = {uid: bool(read) for uid, read in db.query(Notification.user_id, Notification.is_read)
           .filter(Notification.announcement_id == ann.id)}
    since = ann.sent_at - timedelta(days=ACTIVE_DAYS)
    seen: dict[int, int] = {}
    rows = []
    for c in cats:
        members: set[int] = set()
        if (ann.audience or "all") in ("all", "publishers"):
            members |= {u for (u,) in db.query(Task.creator_id).filter(
                Task.category == c, Task.created_at >= since, Task.created_at <= ann.sent_at)}
        if (ann.audience or "all") in ("all", "workers"):
            members |= {u for (u,) in db.query(Application.applicant_id).join(Task, Task.id == Application.task_id).filter(
                Task.category == c, Application.created_at >= since, Application.created_at <= ann.sent_at)}
        hit = [u for u in got if u in members]
        for u in hit:
            seen[u] = seen.get(u, 0) + 1
        read = sum(1 for u in hit if got[u])
        rows.append({"category": c, "delivered": len(hit), "read": read,
                     "read_rate": round(read / len(hit), 3) if hit else None})
    return {**base, "categories": rows, "overlap": sum(1 for v in seen.values() if v > 1), "note": ""}


# NTF-072（261 号 spec）发出后这几个时间点各有多少人点开过
CURVE_POINTS = ((1, "1 小时"), (24, "1 天"), (72, "3 天"), (168, "7 天"))


def read_curve(db: Session, ann: Announcement, now: datetime | None = None) -> dict:
    """NTF-072 阅读率按发出后的时间看：1 小时 / 1 天 / 3 天 / 7 天内点开的累计人数。
    点开时间是 V288 起才记的；之前点开的算进总数、单列为「时间不详」，不硬塞进某个时间点。
    还没到的时间点标 reached=false（数字是到现在为止的）。"""
    from app.modules.notification.models import Notification

    now = now or utcnow()
    base = {"announcement_id": ann.id, "sent_at": iso(ann.sent_at), "delivered": ann.delivered or 0}
    if ann.sent_at is None:
        return {**base, "read": 0, "untimed": 0, "points": [], "note": "这条公告还没发出"}
    rows = db.query(Notification.is_read, Notification.read_at).filter(Notification.announcement_id == ann.id).all()
    read = [r for r in rows if r.is_read]
    timed = [r.read_at for r in read if r.read_at is not None]
    delivered = ann.delivered or 0
    points = []
    for hours, label in CURVE_POINTS:
        n = sum(1 for t in timed if t <= ann.sent_at + timedelta(hours=hours))
        points.append({"hours": hours, "label": label, "read": n,
                       "read_rate": round(n / delivered, 3) if delivered else None,
                       "reached": now >= ann.sent_at + timedelta(hours=hours)})
    untimed = len(read) - len(timed)
    return {**base, "read": len(read), "untimed": untimed, "points": points,
            "note": f"另有 {untimed} 人点开的时间不详（早于记录点开时间的版本），只算进总数" if untimed else ""}


def row(a: Announcement, read: int | None = None) -> dict:
    out = _row(a)
    # NTF-067（159 号 spec）阅读率：已读人数 / 送达人数
    r = read or 0
    out.update({"read": r, "read_rate": round(r / a.delivered, 3) if a.delivered else None})
    return out


def _row(a: Announcement) -> dict:
    return {"id": a.id, "title": a.title, "body": a.body, "verified_only": a.verified_only, "status": a.status,
            "city": a.city or "", "audience": a.audience or "all", "category": a.category or "",
            "scheduled_at": iso(a.scheduled_at), "created_by": a.created_by, "created_at": iso(a.created_at),
            "sent_at": iso(a.sent_at), "delivered": a.delivered, "closed_by": a.closed_by,
            "closed_at": iso(a.closed_at), "close_reason": a.close_reason,
            **({"categories": list(a.categories)} if a.categories else {})}
