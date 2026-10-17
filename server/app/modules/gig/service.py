"""接单者服务包的计算部分（125 号 spec）：附近、顺路（新增绕行）、报价参考、新单推送。

距离一律是**直线距离**（球面），不是道路距离——没有接地图服务；出口都写明「直线估算」。
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.geoutil import haversine_m
from app.modules.account.models import utcnow

from .models import GigAvailability

COARSE = 2                # 坐标保留两位小数：约 1 公里
CANDIDATES = 500
MAX_PUSH_PER_WINDOW = 6   # 一段「有空」里最多推 6 条：推多了就是骚扰
PUSH_TITLE = "附近有新单"


def coarse(x: float) -> float:
    return round(x, COARSE)


def net_cents(budget_cents: int) -> int:
    """扣掉平台服务费后的到手（不含个税代扣，个税按收入性质另算）。"""
    from app.core.config import settings

    return budget_cents - budget_cents * settings.PLATFORM_FEE_BPS // 10000


def active(db: Session, user_id: int) -> GigAvailability | None:
    """到点的「有空」直接删掉：位置不留着过夜。"""
    a = db.get(GigAvailability, user_id)
    if a is not None and a.until <= utcnow():
        db.delete(a)
        db.flush()
        return None
    return a


# SCN-129（192 号 spec）名额写着「哪天几点到几点」（北京时间）。时段已经过去的不推；开着「现在有空」时，
# 只推与「现在 → 有空截止」对得上的名额——推一个下周三的名额给「接下来两小时有空」的人，等于白跑一趟。
_CN = ZoneInfo("Asia/Shanghai")


def slot_window(t) -> tuple[datetime, datetime] | None:
    """名额那天的时段换成 UTC（无时区，与库里一致）；不是按天的名额返回 None。没写时段按整天。"""
    if not getattr(t, "work_date", None):
        return None

    def at(hm: str) -> datetime:
        h, m = (int(x) for x in hm.split(":"))
        local = datetime.combine(t.work_date, time(0, 0), tzinfo=_CN) + timedelta(hours=h, minutes=m)
        return local.astimezone(timezone.utc).replace(tzinfo=None)

    return at(t.shift_start or "00:00"), at(t.shift_end or "24:00")


def fits_window(t, window: tuple[datetime, datetime] | None, now: datetime) -> bool:
    w = slot_window(t)
    if w is None:
        return True
    if w[1] <= now:
        return False
    return window is None or (w[0] < window[1] and w[1] > window[0])


def _open_tasks(db: Session, user_id: int, categories: list[str] | None = None,
                window: tuple[datetime, datetime] | None = None):
    from app.modules.task.models import Task

    now = utcnow()
    q = db.query(Task).filter(Task.status == "published", Task.visibility == "public", Task.is_remote.is_(False),
                              Task.lat.isnot(None), Task.lng.isnot(None), Task.creator_id != user_id,
                              (Task.deadline.is_(None)) | (Task.deadline > now))
    if categories:
        q = q.filter(Task.category.in_(categories))
    return [t for t in q.order_by(Task.id.desc()).limit(CANDIDATES).all() if fits_window(t, window, now)]


def _card(t, **extra) -> dict:
    from app.core.timefmt import day, iso

    return {"task_id": t.id, "title": t.title, "category": t.category, "budget_cents": t.budget_cents,
            "net_cents": net_cents(t.budget_cents), "address_hint": t.address_hint, "city": t.city,
            "deadline": iso(t.deadline), "work_date": day(t.work_date), "shift_start": t.shift_start or "",
            "shift_end": t.shift_end or "", **extra}


def nearby(db: Session, user_id: int, lat: float, lng: float, radius_km: int, categories: list[str] | None,
           limit: int = 20, window: tuple[datetime, datetime] | None = None) -> list[dict]:
    """半径内、按距离排序；同距离档（500 米一档）里报酬高的在前。"""
    out = []
    for t in _open_tasks(db, user_id, categories, window):
        d = haversine_m(lat, lng, t.lat, t.lng)
        if d <= radius_km * 1000:
            out.append((round(d / 500), -t.budget_cents, t.id, t, round(d)))
    out.sort(key=lambda x: x[:3])
    return [_card(t, distance_m=d) for *_, t, d in out[:limit]]


def along(db: Session, user_id: int, src: tuple[float, float], dst: tuple[float, float], max_detour_km: float,
          categories: list[str] | None, limit: int = 20, window: tuple[datetime, datetime] | None = None) -> list[dict]:
    """顺路单：任务点 T 让「起点 → 终点」多走的路 = d(O,T) + d(T,D) − d(O,D)。按多走的少排序。

    业界的同一思路：即时配送派单看的是「插进这一单之后路线增加了多少」，不是离骑手多近
    （125 号 spec 第 1 节）。这里没有道路数据，用直线距离估。
    """
    base = haversine_m(*src, *dst)
    out = []
    for t in _open_tasks(db, user_id, categories, window):
        detour = haversine_m(*src, t.lat, t.lng) + haversine_m(t.lat, t.lng, *dst) - base
        if detour <= max_detour_km * 1000:
            out.append((round(detour), -t.budget_cents, t.id, t, round(haversine_m(*src, t.lat, t.lng))))
    out.sort(key=lambda x: x[:3])
    return [_card(t, detour_m=dm, from_start_m=fs) for dm, _, _, t, fs in out[:limit]]


def quote(db: Session, category: str, city: str | None, budget_cents: int | None) -> dict:
    """报价参考：同类目近 180 天闭环成交价的分布（KB-021），对照预算，算出到手。不是模型猜的价。"""
    from app.modules.knowledge.service import price_reference

    ref = price_reference(db, category, city or None)
    scope = f"{city}·{category}" if city else category
    if not ref.get("sample_size") and city:
        ref = price_reference(db, category, None)
        scope = f"{category}（{city}暂无数据，用全平台）"
    basis: list[str] = []
    if ref.get("sample_size"):
        p50 = ref["p50_cents"]
        basis.append(f"{scope}近 180 天 {ref['sample_size']} 单成交，中位 ¥{p50 / 100:.2f}，"
                     f"最低 ¥{ref['min_cents'] / 100:.2f}，最高 ¥{ref['max_cents'] / 100:.2f}")
        if budget_cents:
            diff = (budget_cents - p50) * 100 // p50
            basis.append(f"这一单预算 ¥{budget_cents / 100:.2f}，" +
                         (f"比中位高 {diff}%" if diff > 0 else f"比中位低 {-diff}%" if diff < 0 else "与中位持平"))
        suggested = budget_cents if budget_cents and budget_cents >= p50 else p50
    else:
        basis.append(f"{scope}还没有足够的成交数据，按发布方预算报价")
        suggested = budget_cents or 0
    if suggested:
        basis.append(f"按 ¥{suggested / 100:.2f} 报价，扣平台服务费后到手约 ¥{net_cents(suggested) / 100:.2f}（个税另按规定代扣）")
    return {"category": category, "city": city or "", "sample_size": ref.get("sample_size", 0),
            "p50_cents": ref.get("p50_cents"), "min_cents": ref.get("min_cents"), "max_cents": ref.get("max_cents"),
            "budget_cents": budget_cents, "suggested_cents": suggested or None,
            "net_cents": net_cents(suggested) if suggested else None, "basis": basis,
            "disclaimer": "报价参考来自平台成交数据，不是承诺价；报不报、报多少由你决定。"}


def on_task_published(db: Session, payload: dict) -> None:
    """新单发布：通知「现在有空」、半径覆盖到、类目对得上的人。每段「有空」最多推 6 条。"""
    from app.modules.notification.service import notify
    from app.modules.task.models import Task

    t = db.get(Task, payload["task_id"])
    if t is None or t.visibility != "public" or t.is_remote or t.lat is None or t.lng is None:
        return
    now = utcnow()
    rows = (db.query(GigAvailability).filter(GigAvailability.until > now, GigAvailability.user_id != t.creator_id,
                                             GigAvailability.pushed < MAX_PUSH_PER_WINDOW)
            .limit(5000).all())
    for a in rows:
        if a.categories and t.category not in a.categories:
            continue
        if not fits_window(t, (now, a.until), now):      # SCN-129 名额的时段与这段「有空」对不上
            continue
        d = haversine_m(a.lat, a.lng, t.lat, t.lng)
        if d > a.radius_km * 1000:
            continue
        notify(db, a.user_id, "task", PUSH_TITLE,
               f"《{t.title}》{t.category} · 约 {d / 1000:.1f} 公里（直线）· 预算 ¥{t.budget_cents / 100:.2f}，到手约 ¥{net_cents(t.budget_cents) / 100:.2f}")
        a.pushed += 1
        db.add(a)


def purge_expired(db: Session) -> int:
    """过期的「有空」连同位置一起删（job 每小时一次；读的时候也会顺手删）。"""
    cutoff = utcnow() - timedelta(minutes=1)
    n = db.query(GigAvailability).filter(GigAvailability.until <= cutoff).delete(synchronize_session=False)
    return int(n or 0)


def register_event_handlers() -> None:
    from app.core.events import subscribe

    subscribe("task.published", on_task_published, retry=True)
