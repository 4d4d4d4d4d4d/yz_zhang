"""GIG-100 接单者工具接口（125 号 spec）。全部只作用于调用者本人；坐标入库前粗化到约 1 公里。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, conflict, not_found
from app.core.locks import job_slot
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import GigAvailability, GigPlace, GigRoute

router = APIRouter(tags=["gig"])
MAX_PLACES = 10
MAX_ROUTES = 5      # SCN-140 常用路线最多 5 条：每条每天最多推一次


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AvailableIn(_In):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    radius_km: int = Field(default=5, ge=1, le=30)
    hours: int = Field(default=2, ge=1, le=12)
    categories: list[str] = Field(default_factory=list, max_length=10)


class PlaceIn(_In):
    name: str = Field(min_length=1, max_length=20)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RouteIn(_In):
    """SCN-140 常用路线：从哪个常用地点、到哪个、哪几天（0 = 星期一）、几点出发（北京时间）、之后几小时内的名额。"""
    from_place: int
    to_place: int
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    depart_hm: str = Field(max_length=8)
    within_hours: int = Field(default=3, ge=1, le=12)


class QuoteIn(_In):
    task_id: int | None = None
    category: str = Field(default="", max_length=50)
    city: str = Field(default="", max_length=50)


def _dump_avail(a: GigAvailability | None) -> dict:
    if a is None:
        return {"available": False, "until": None, "radius_km": None, "categories": [], "pushed": 0}
    return {"available": True, "until": iso(a.until), "radius_km": a.radius_km, "categories": a.categories or [],
            "pushed": a.pushed}


def _dump_place(p: GigPlace) -> dict:
    return {"id": p.id, "name": p.name, "lat": p.lat, "lng": p.lng}


def _own_place(db: Session, place_id: int, user: User) -> GigPlace:
    p = db.get(GigPlace, place_id)
    if p is None or p.owner_id != user.id:
        raise not_found("这个地点不存在")
    return p


# ------------------------------------------------------------------ 现在有空（GIG-101）
@router.get("/gig/available")
def get_available(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return _dump_avail(svc.active(db, user.id))


@router.put("/gig/available")
def set_available(body: AvailableIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    """接下来几个小时有空：附近有新单就推给我（最多 6 条）。到点自动失效，位置随之删除。"""
    a = db.get(GigAvailability, user.id) or GigAvailability(user_id=user.id)
    a.lat, a.lng = svc.coarse(body.lat), svc.coarse(body.lng)
    a.radius_km, a.categories = body.radius_km, list(dict.fromkeys(c.strip() for c in body.categories if c.strip()))
    a.until, a.pushed, a.updated_at = utcnow() + timedelta(hours=body.hours), 0, utcnow()
    db.add(a)
    db.flush()
    return _dump_avail(a)


@router.delete("/gig/available")
def stop_available(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    a = db.get(GigAvailability, user.id)
    if a is not None:
        db.delete(a)
    return _dump_avail(None)


# ------------------------------------------------------------------ 附近与顺路（GIG-102 / 103）
@router.get("/gig/nearby")
def get_nearby(lat: float | None = Query(default=None, ge=-90, le=90), lng: float | None = Query(default=None, ge=-180, le=180),
               radius_km: int | None = Query(default=None, ge=1, le=30),
               user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """不给坐标时用「现在有空」里的位置；都没有就 400（不猜位置）。坐标只用于这次计算。"""
    a = svc.active(db, user.id)
    if lat is None or lng is None:
        if a is None:
            raise bad_request("先打开「现在有空」，或者带上当前位置", "gig_need_location")
        lat, lng = a.lat, a.lng
    r = radius_km or (a.radius_km if a else 5)
    window = (utcnow(), a.until) if a else None      # SCN-129 开着「现在有空」：只看这段时间对得上的名额
    return {"radius_km": r, "items": svc.nearby(db, user.id, lat, lng, r, a.categories if a else None, window=window),
            "notice": "距离是直线估算，不是道路距离"}


@router.get("/gig/along")
def get_along(from_place: int | None = None, to_place: int | None = None,
              from_lat: float | None = Query(default=None, ge=-90, le=90),
              from_lng: float | None = Query(default=None, ge=-180, le=180),
              max_detour_km: float = Query(default=2, gt=0, le=20),
              depart_at: str | None = Query(default=None, max_length=32),
              within_hours: int = Query(default=3, ge=1, le=12),
              user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """顺路单：从当前位置（或一个常用地点）到另一个常用地点，顺路能接哪些单。

    SCN-134（203 号 spec）可带出发时间（北京时间，如 2026-10-18T08:30）：只看出发后 within_hours 小时内对得上的名额，
    不再按「现在有空」那一段——明早上班顺路带一单，今晚就能先看。"""
    if to_place is None:
        raise bad_request("选一个目的地（常用地点）", "gig_need_destination")
    dst = _own_place(db, to_place, user)
    if from_place is not None:
        src_p = _own_place(db, from_place, user)
        src = (src_p.lat, src_p.lng)
    elif from_lat is not None and from_lng is not None:
        src = (from_lat, from_lng)
    else:
        raise bad_request("起点用当前位置或一个常用地点", "gig_need_location")
    a = svc.active(db, user.id)
    window = (utcnow(), a.until) if a else None
    if depart_at:
        start = _depart_utc(depart_at)
        window = (start, start + timedelta(hours=within_hours))
    return {"to": dst.name, "max_detour_km": max_detour_km,
            "items": svc.along(db, user.id, src, (dst.lat, dst.lng), max_detour_km, a.categories if a else None,
                               window=window),
            "depart_at": depart_at.strip() if depart_at else None, "within_hours": within_hours if depart_at else None,
            "notice": "多走的路是直线估算（起点→任务点→终点 比 起点→终点 多出的距离）"}


# 出发时间最早可以写成一刻钟前（刚出门才想起来看），最晚一周后：再往后的名额还会变，看了也不准
DEPART_GRACE_MINUTES = 15
DEPART_MAX_DAYS = 7


def _depart_utc(raw: str) -> datetime:
    """出发时间换成 UTC（无时区，与库里一致）。没写时区的按北京时间。"""
    try:
        t = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise bad_request("出发时间写成 2026-10-18T08:30 这样（北京时间）", "gig_depart_invalid") from None
    if t.tzinfo is None:
        t = t.replace(tzinfo=svc._CN)
    t = t.astimezone(timezone.utc).replace(tzinfo=None)
    now = utcnow()
    if t < now - timedelta(minutes=DEPART_GRACE_MINUTES):
        raise bad_request("出发时间已经过去了：改成现在以后的时间，或者不填（按「现在有空」）", "gig_depart_past")
    if t > now + timedelta(days=DEPART_MAX_DAYS):
        raise bad_request(f"出发时间最多看 {DEPART_MAX_DAYS} 天以内的：再往后的名额还会变", "gig_depart_too_far")
    return t


# ------------------------------------------------------------------ 常用地点
@router.get("/gig/places")
def list_places(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return [_dump_place(p) for p in db.query(GigPlace).filter(GigPlace.owner_id == user.id).order_by(GigPlace.id)]


@router.post("/gig/places", status_code=201)
def add_place(body: PlaceIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    if (db.query(func.count(GigPlace.id)).filter(GigPlace.owner_id == user.id).scalar() or 0) >= MAX_PLACES:
        raise conflict(f"常用地点最多 {MAX_PLACES} 个，先删掉不用的", "gig_places_full")
    p = GigPlace(owner_id=user.id, name=body.name.strip(), lat=svc.coarse(body.lat), lng=svc.coarse(body.lng))
    db.add(p)
    db.flush()
    return _dump_place(p)


@router.delete("/gig/places/{place_id}")
def delete_place(place_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    db.delete(_own_place(db, place_id, user))
    # SCN-140 用到这个地点的常用路线一起删：起点终点都没了，路线没有意义
    db.query(GigRoute).filter(GigRoute.owner_id == user.id,
                              (GigRoute.from_place_id == place_id) | (GigRoute.to_place_id == place_id)).delete(
        synchronize_session=False)
    return {"deleted": True}


# ------------------------------------------------------------------ 常用路线（SCN-140）
def _dump_route(db: Session, r: GigRoute) -> dict:
    names = {p.id: p.name for p in db.query(GigPlace).filter(GigPlace.id.in_([r.from_place_id, r.to_place_id]))}
    return {"id": r.id, "from_place": r.from_place_id, "to_place": r.to_place_id,
            "from_name": names.get(r.from_place_id, ""), "to_name": names.get(r.to_place_id, ""),
            "weekdays": list(r.weekdays or []), "depart_hm": r.depart_hm, "within_hours": r.within_hours}


@router.get("/gig/routes")
def list_routes(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return [_dump_route(db, r) for r in db.query(GigRoute).filter(GigRoute.owner_id == user.id).order_by(GigRoute.id)]


@router.post("/gig/routes", status_code=201)
def add_route(body: RouteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """存一条常用路线：出发前一小时内推一次顺路的名额（一天一次）。"""
    import re

    _own_place(db, body.from_place, user)
    _own_place(db, body.to_place, user)
    if body.from_place == body.to_place:
        raise bad_request("起点和终点要是两个不同的常用地点", "gig_route_same_place")
    days = sorted({d for d in body.weekdays if 0 <= d <= 6})
    if not days or len(days) != len(set(body.weekdays)):
        raise bad_request("选上哪几天走这条路（星期一到星期日）", "gig_route_no_days")
    hm = body.depart_hm.strip()
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", hm):
        raise bad_request("出发时间按 24 小时制写成 HH:MM（例如 08:30）", "gig_route_time_invalid")
    if (db.query(func.count(GigRoute.id)).filter(GigRoute.owner_id == user.id).scalar() or 0) >= MAX_ROUTES:
        raise conflict(f"常用路线最多 {MAX_ROUTES} 条，先删掉不走的", "gig_routes_full")
    r = GigRoute(owner_id=user.id, from_place_id=body.from_place, to_place_id=body.to_place, weekdays=days,
                 depart_hm=hm, within_hours=body.within_hours)
    db.add(r)
    db.flush()
    return _dump_route(db, r)


@router.delete("/gig/routes/{route_id}")
def delete_route(route_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    r = db.get(GigRoute, route_id)
    if r is None or r.owner_id != user.id:
        raise not_found("这条路线不存在")
    db.delete(r)
    return {"deleted": True}


# ------------------------------------------------------------------ 报价参考（GIG-104）
@router.post("/gig/quote")
def post_quote(body: QuoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """给一单（或一个类目）报价参考。只读公开招募中的任务：别人的草稿、私有任务不给看。"""
    if body.task_id is not None:
        from app.modules.task.models import Task

        t = db.get(Task, body.task_id)
        if t is None or (t.creator_id != user.id and (t.status != "published" or t.visibility != "public")):
            raise not_found("任务不存在")
        return {"task_id": t.id, **svc.quote(db, t.category, t.city, t.budget_cents)}
    if not body.category.strip():
        raise bad_request("给一个任务，或者一个类目", "gig_quote_needs_subject")
    return {"task_id": None, **svc.quote(db, body.category.strip(), body.city.strip() or None, None)}


@router.post("/gig/jobs/route-push")
def job_route_push(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                   __=Depends(job_slot("gig_route_push"), scope="function")):
    return svc.push_routes(db)


@router.post("/gig/jobs/purge-expired")
def job_purge(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
              __=Depends(job_slot("gig_purge"), scope="function")):
    return {"purged": svc.purge_expired(db)}
