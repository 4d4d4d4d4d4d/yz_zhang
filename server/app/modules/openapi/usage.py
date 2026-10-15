"""API-052 API Key 用量与每日配额（152 号 spec）。

V173 有了每分钟限流，但集成方仍然看不到自己用了多少；平台也没有「一天最多多少次」——
一个跑飞的循环在限流之内照样能一天打几十万次。

- 每把 Key 每天（北京时间）一行：真正进到接口的 `count`，被每分钟限流或每日配额挡回去的 `rejected`；
- 配额先加后判：加一之后超了就撤回这一次、记一次 rejected、回 429 并告诉他到北京时间几点恢复。
  用 `UPDATE … SET count = count + 1` 而不是先读后写，并发请求在行锁上排队，不会一起溜过最后一格；
- 用量是独立的记账事实，当场提交（与「最近使用时间」同一个理由），被挡回去的那次也要留下。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timefmt import day as day_str, iso
from app.modules.account.models import utcnow
from app.modules.workbench.service import _back, local

from .models import ApiKey, ApiKeyUsage

USAGE_DAYS_MAX = 90


def day_of(now: datetime) -> str:
    return day_str(local(now).date())


def next_reset(now: datetime) -> datetime:
    """下一个北京时间零点（UTC 朴素值）。"""
    d = local(now)
    midnight = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return _back(midnight)


def effective_quota(key: ApiKey) -> int:
    cap = settings.API_KEY_DAILY_QUOTA
    return min(key.daily_quota, cap) if key.daily_quota and key.daily_quota > 0 else cap


def _bump(db: Session, key_id: int, day: str, field: str, delta: int = 1) -> None:
    col = getattr(ApiKeyUsage, field)
    n = (db.query(ApiKeyUsage).filter(ApiKeyUsage.key_id == key_id, ApiKeyUsage.day == day)
         .update({col: col + delta}, synchronize_session=False))
    if n:
        return
    try:
        with db.begin_nested():
            db.add(ApiKeyUsage(key_id=key_id, day=day, count=delta if field == "count" else 0,
                               rejected=delta if field == "rejected" else 0))
    except IntegrityError:      # 并发的另一个请求刚插了这一天
        (db.query(ApiKeyUsage).filter(ApiKeyUsage.key_id == key_id, ApiKeyUsage.day == day)
         .update({col: col + delta}, synchronize_session=False))


def _used(db: Session, key_id: int, day: str) -> int:
    row = db.query(ApiKeyUsage).filter(ApiKeyUsage.key_id == key_id, ApiKeyUsage.day == day).first()
    return row.count if row else 0


def record_rejected(db: Session, key_id: int, now: datetime | None = None) -> None:
    from app.vendors.base import checkpoint

    _bump(db, key_id, day_of(now or utcnow()), "rejected")
    checkpoint(db, "被挡回去的 API 请求也是独立的用量记账，回 429 之前当场提交")


def consume(db: Session, key: ApiKey, now: datetime | None = None) -> tuple[int, int]:
    """记一次用量并核对每日配额。返回 (今天已用, 配额)；超了返回 used > limit，由调用方回 429。"""
    from app.vendors.base import checkpoint

    now = now or utcnow()
    day, limit = day_of(now), effective_quota(key)
    _bump(db, key.id, day, "count")
    db.flush()
    used = _used(db, key.id, day)
    if used > limit:
        _bump(db, key.id, day, "count", -1)
        _bump(db, key.id, day, "rejected")
    checkpoint(db, "API Key 当日用量是独立记账，鉴权时当场提交（与最近使用时间同一个理由）")
    return used, limit


def carry_today(db: Session, old_id: int, new_id: int, now: datetime | None = None) -> None:
    """轮换不清零当天用量：否则轮换一次就绕过了每日配额。"""
    day = day_of(now or utcnow())
    used = _used(db, old_id, day)
    if used:
        _bump(db, new_id, day, "count", used)


def view(db: Session, key: ApiKey, days: int = 14, now: datetime | None = None) -> dict:
    now = now or utcnow()
    days = max(1, min(days, USAGE_DAYS_MAX))
    today = local(now).date()
    wanted = [day_str(today - timedelta(days=i)) for i in range(days)]
    rows = {r.day: r for r in db.query(ApiKeyUsage)
            .filter(ApiKeyUsage.key_id == key.id, ApiKeyUsage.day.in_(wanted)).all()}
    limit = effective_quota(key)
    used = rows[wanted[0]].count if wanted[0] in rows else 0
    return {
        "key_id": key.id, "daily_quota": key.daily_quota, "effective_daily_quota": limit,
        "today": wanted[0], "today_used": used, "today_remaining": max(0, limit - used),
        "resets_at": iso(next_reset(now)), "time_zone": "北京时间 UTC+8",
        "days": [{"day": d, "count": rows[d].count if d in rows else 0,
                  "rejected": rows[d].rejected if d in rows else 0} for d in wanted],
    }
