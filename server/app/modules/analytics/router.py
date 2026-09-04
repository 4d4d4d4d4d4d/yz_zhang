from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.modules.account.models import User

from . import service

router = APIRouter(tags=["analytics"])


class TrackIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    ref_type: str = ""
    ref_id: int | None = None


@router.post("/events", status_code=201)
def track_event(body: TrackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """13.C 埋点上报（客户端漏斗事件）。"""
    service.track(db, body.name, user.id, body.ref_type, body.ref_id)
    return {"ok": True}


@router.get("/admin/funnels")
def funnels(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """13.C 发布漏斗 + 接单漏斗看板（运营）。"""
    return service.funnels(db)


@router.get("/search/trending")
def trending(db: Session = Depends(get_db), limit: int = Query(default=10, le=50)):
    """SRCH-003 热门搜索词。"""
    return service.trending_terms(db, limit)


@router.get("/search/suggest")
def suggest(q: str = "", db: Session = Depends(get_db)):
    """SRCH-003 搜索联想。"""
    return service.suggest_terms(db, q.strip())
