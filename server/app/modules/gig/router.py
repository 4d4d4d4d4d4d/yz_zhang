"""GIG-100 接单者工具接口（125 号 spec）。全部只作用于调用者本人；坐标入库前粗化到约 1 公里。"""
from __future__ import annotations

from datetime import timedelta

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
from .models import GigAvailability, GigPlace

router = APIRouter(tags=["gig"])
MAX_PLACES = 10


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
    return {"radius_km": r, "items": svc.nearby(db, user.id, lat, lng, r, a.categories if a else None),
            "notice": "距离是直线估算，不是道路距离"}


@router.get("/gig/along")
def get_along(from_place: int | None = None, to_place: int | None = None,
              from_lat: float | None = Query(default=None, ge=-90, le=90),
              from_lng: float | None = Query(default=None, ge=-180, le=180),
              max_detour_km: float = Query(default=2, gt=0, le=20),
              user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """顺路单：从当前位置（或一个常用地点）到另一个常用地点，顺路能接哪些单。"""
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
    return {"to": dst.name, "max_detour_km": max_detour_km,
            "items": svc.along(db, user.id, src, (dst.lat, dst.lng), max_detour_km, a.categories if a else None),
            "notice": "多走的路是直线估算（起点→任务点→终点 比 起点→终点 多出的距离）"}


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


@router.post("/gig/jobs/purge-expired")
def job_purge(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
              __=Depends(job_slot("gig_purge"), scope="function")):
    return {"purged": svc.purge_expired(db)}
