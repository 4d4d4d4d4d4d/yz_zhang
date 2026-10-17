from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_optional_user, require_job_auth
from app.core.locks import job_slot
from app.core.admin_roles import require_role
from app.modules.account.models import User

from . import service

router = APIRouter(tags=["analytics"])


class TrackIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    ref_type: str = ""
    ref_id: int | None = None


@router.post("/events", status_code=201)
def track_event(body: TrackIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """13.C 埋点上报（客户端漏斗事件）。"""
    service.track(db, body.name, user.id, body.ref_type, body.ref_id)
    return {"ok": True}


class RenderErrorIn(BaseModel):
    """APP-094 一页 / 一屏渲染出错：只有平台、页面、错误类型，不收错误内容。"""
    model_config = ConfigDict(extra="forbid")
    platform: Literal["web", "app"]
    page: str = Field(max_length=40)
    kind: str = Field(default="Error", max_length=40)


@router.post("/client-errors", status_code=201)
def report_render_error(body: RenderErrorIn, user: User | None = Depends(get_optional_user),
                        db: Session = Depends(get_db, scope="function")):
    """APP-094（184 号 spec）两端错误边界接住渲染错误后上报。登录与否都收（登录页也可能坏）；
    带 token 时记是谁，只用于数「不同的人」；同一人同一页同类错误一分钟内只记一次。"""
    recorded = service.report_render_error(db, user.id if user else None, body.platform, body.page, body.kind)
    return {"ok": True, "recorded": recorded}


@router.get("/admin/client-errors")
def client_errors(days: int = Query(default=7, ge=1, le=90), admin: User = Depends(require_role("ops")),
                  db: Session = Depends(get_db, scope="function")):
    """APP-094 哪一页常坏（运营）：平台 × 页面 × 错误类型的次数、人数、最近一次。"""
    return service.render_errors(db, days)


@router.post("/analytics/jobs/render-alerts")
def job_render_alerts(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                      __=Depends(job_slot("render_alerts"), scope="function")):
    """APP-097 每小时：同一页 24 小时内坏过的人到阈值就提醒运营（同一页 24 小时内只一次）。"""
    return {"alerted": service.render_alerts(db)}


@router.get("/admin/funnels")
def funnels(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """13.C 发布漏斗 + 接单漏斗看板（运营）。"""
    return service.funnels(db)


@router.get("/search/trending")
def trending(db: Session = Depends(get_db, scope="function"), limit: int = Query(default=10, le=50)):
    """SRCH-003 热门搜索词。"""
    return service.trending_terms(db, limit)


@router.get("/search/suggest")
def suggest(q: str = "", db: Session = Depends(get_db, scope="function")):
    """SRCH-003 搜索联想。"""
    return service.suggest_terms(db, q.strip())
