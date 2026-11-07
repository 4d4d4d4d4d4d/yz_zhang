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

from .models import ApiAccountQuota, ApiKey, ApiKeyUsage

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


def account_used(db: Session, user_id: int, day: str) -> int:
    """API-054 同一账号所有 Key（含已吊销、已轮换的）当天进来的次数合计。"""
    from sqlalchemy import func

    total = (db.query(func.coalesce(func.sum(ApiKeyUsage.count), 0))
             .join(ApiKey, ApiKey.id == ApiKeyUsage.key_id)
             .filter(ApiKey.user_id == user_id, ApiKeyUsage.day == day).scalar())
    return int(total or 0)


def consume(db: Session, key: ApiKey, now: datetime | None = None) -> tuple[int, int]:
    """记一次用量并核对每日配额。返回 (今天已用, 配额)；超了返回 used > limit，由调用方回 429。

    API-054（158 号 spec）账号合计也要在账号配额以内；超了同样撤回这一次、记一次 rejected，
    返回值里用 `account_over` 区分（见 `consume_ex`）。"""
    used, limit, _acct = consume_ex(db, key, now)
    return used, limit


def account_quota(db: Session, user_id: int, now: datetime | None = None) -> tuple[int, ApiAccountQuota | None]:
    """API-056（235 号 spec）这个账号当前生效的每日总配额：单独调过且没过期的用调过的，否则用默认。"""
    now = now or utcnow()
    row = db.query(ApiAccountQuota).filter(ApiAccountQuota.user_id == user_id).first()
    if row is not None and (row.expires_at is None or row.expires_at > now):
        return row.daily_quota, row
    return settings.API_ACCOUNT_DAILY_QUOTA, None


def consume_ex(db: Session, key: ApiKey, now: datetime | None = None) -> tuple[int, int, dict]:
    from app.vendors.base import checkpoint

    now = now or utcnow()
    day, limit = day_of(now), effective_quota(key)
    acct_limit, _custom = account_quota(db, key.user_id, now)
    _bump(db, key.id, day, "count")
    db.flush()
    used = _used(db, key.id, day)
    acct = account_used(db, key.user_id, day)
    over_key, over_acct = used > limit, acct > acct_limit
    if over_key or over_acct:
        _bump(db, key.id, day, "count", -1)
        _bump(db, key.id, day, "rejected")
    checkpoint(db, "API Key 当日用量是独立记账，鉴权时当场提交（与最近使用时间同一个理由）")
    return used, limit, {"used": acct, "limit": acct_limit, "over": over_acct and not over_key}


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
    acct_limit, custom = account_quota(db, key.user_id, now)
    acct_used = account_used(db, key.user_id, wanted[0])
    return {
        # API-054（158 号 spec）账号所有 Key 当天合计
        "account_today_used": acct_used, "account_daily_quota": acct_limit,
        "account_today_remaining": max(0, acct_limit - acct_used),
        # API-056（235 号 spec）账号配额是不是平台给你单独调过的、到哪天
        "account_quota_custom": custom is not None,
        "account_quota_expires_at": iso(custom.expires_at) if custom is not None else None,
        "key_id": key.id, "daily_quota": key.daily_quota, "effective_daily_quota": limit,
        "today": wanted[0], "today_used": used, "today_remaining": max(0, limit - used),
        "resets_at": iso(next_reset(now)), "time_zone": "北京时间 UTC+8",
        "days": [{"day": d, "count": rows[d].count if d in rows else 0,
                  "rejected": rows[d].rejected if d in rows else 0} for d in wanted],
    }


def purge_usage(db: Session, now: datetime | None = None) -> dict:
    """API-055（219 号 spec）用量页最多看 90 天，更早的用量行留着没有用处：按北京日期清掉。
    当天与近 90 天的不动（每日配额读的是当天那一行）。"""
    cutoff = day_of((now or utcnow()) - timedelta(days=USAGE_DAYS_MAX))
    n = db.query(ApiKeyUsage).filter(ApiKeyUsage.day < cutoff).delete(synchronize_session=False)
    return {"purged": int(n or 0), "kept_from": cutoff}
