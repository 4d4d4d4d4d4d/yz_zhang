"""SCN-122（356 号 spec）服务对象自己看进度：替别人发单时的免登录只读链接。

子女替爸妈发单（SCN-119，175 号）后，爸妈最常问的是「人几点来、来了没有」。短信通道要持牌服务商（「外」），
这里先做平台内能做的那一半：发单人生成一条链接，用微信等自己的渠道发给服务对象，对方不用注册、不用登录就能看。

- 只有替别人发的单能生成；只有发单人本人能生成、查看状态、作废。
- 令牌只在生成时返回一次，库里只存哈希；一单同时只有一条有效链接，重新生成即作废旧的。
- 有效期 1~14 天（默认 7 天），到期或作废后打不开；单子结束后还能看，直到到期。
- 链接页只给：服务对象的称呼、单子标题、进展、接单人的昵称与是否实名、约定的日子与时段、上门回报了几次、最近一次到达时间。
  **不给**手机号、精确地址、价钱、聊天、照片与位置。
- 按来访 IP 限流；发单人能看到被打开过几次、最近一次什么时候。
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.clientip import client_ip
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from .models import ProgressLog, RecipientLink, Task

router = APIRouter(tags=["task"])

DEFAULT_DAYS = 7
MAX_DAYS = 14
VIEWS_PER_MINUTE = 30     # 每个来访 IP 每分钟最多打开这么多次（防撞令牌、防刷）
CLOSED = ("completed", "cancelled")

PHASE_TEXT = {
    "waiting": "还在找人，定好了会显示是谁来",
    "assigned": "已经定好人了",
    "working": "已经开始了",
    "done_pending": "做完了，等发单的家人确认",
    "done": "已经完成",
    "cancelled": "这一单取消了",
    "paused": "发单的家人正在和接单人沟通，暂时停一下",
}
_STATUS_PHASE = {"draft": "waiting", "published": "waiting", "matched": "assigned", "in_progress": "working",
                 "pending_acceptance": "done_pending", "completed": "done", "cancelled": "cancelled",
                 "disputed": "paused"}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _state(r: RecipientLink | None) -> str:
    if r is None:
        return "none"
    return "revoked" if r.revoked_at else "expired" if r.expires_at <= utcnow() else "active"


def link_row(r: RecipientLink | None) -> dict:
    """发单人看到的链接状态（不含令牌）；也用于数据导出。"""
    return {"state": _state(r), "task_id": r.task_id if r else None,
            "created_at": iso(r.created_at) if r else None, "expires_at": iso(r.expires_at) if r else None,
            "view_count": r.view_count if r else 0, "last_viewed_at": iso(r.last_viewed_at) if r else None}


def _own_task(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if task.creator_id != user.id:
        raise forbidden("只有发单人本人能管理服务对象的进度链接", "recipient_link_not_owner")
    return task


def _latest(db: Session, task_id: int) -> RecipientLink | None:
    return db.query(RecipientLink).filter(RecipientLink.task_id == task_id).order_by(RecipientLink.id.desc()).first()


class RecipientLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: int = Field(default=DEFAULT_DAYS, ge=1, le=MAX_DAYS)


@router.post("/tasks/{task_id}/recipient-link", status_code=201)
def create_link(task_id: int, body: RecipientLinkIn | None = None, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    """令牌只在这个响应里出现一次；重新生成即作废这一单之前的链接。"""
    task = _own_task(db, task_id, user)
    if not task.on_behalf:
        raise bad_request("只有替别人发的单才能生成服务对象的进度链接：自己的单在「我发的任务」里看进度就行",
                          "recipient_link_not_on_behalf")
    if task.status in CLOSED:
        raise conflict("这一单已经结束了，不用再给服务对象发进度链接", "recipient_link_task_closed")
    now = utcnow()
    db.query(RecipientLink).filter(RecipientLink.task_id == task_id, RecipientLink.revoked_at.is_(None)).update(
        {"revoked_at": now}, synchronize_session=False)
    token = secrets.token_urlsafe(24)
    days = body.days if body else DEFAULT_DAYS
    row = RecipientLink(task_id=task_id, created_by=user.id, token_hash=_hash(token), expires_at=now + timedelta(days=days))
    db.add(row)
    db.flush()
    return {**link_row(row), "token": token, "path": f"/r/{token}",
            "hint": "用微信等发给服务对象本人；对方不用登录就能看谁来、几点、到没到，看不到电话、地址和价钱"}


@router.get("/tasks/{task_id}/recipient-link")
def get_link(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    _own_task(db, task_id, user)
    return link_row(_latest(db, task_id))


@router.delete("/tasks/{task_id}/recipient-link")
def revoke_link(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    _own_task(db, task_id, user)
    n = db.query(RecipientLink).filter(RecipientLink.task_id == task_id, RecipientLink.revoked_at.is_(None)).update(
        {"revoked_at": utcnow()}, synchronize_session=False)
    db.flush()
    return {**link_row(_latest(db, task_id)), "revoked": n}


def _phase(task: Task, slots: list[Task]) -> str:
    if not slots:
        return _STATUS_PHASE.get(task.status, "waiting")
    phases = [_STATUS_PHASE.get(s.status, "waiting") for s in slots]
    live = [p for p in phases if p != "cancelled"]
    if not live:
        return "cancelled"
    for p in ("paused", "working", "done_pending"):
        if p in live:
            return p
    if all(p == "done" for p in live):
        return "done"
    return "assigned" if any(p in ("assigned", "done") for p in live) else "waiting"


def _helper(u: User | None) -> dict:
    if u is None or u.is_deleted:
        return {"name": "接单人", "verified": False}
    return {"name": u.nickname or "接单人", "verified": bool(u.is_verified)}


@router.get("/recipient-progress/{token}")
def recipient_progress(token: str, request: Request, db: Session = Depends(get_db, scope="function")):
    """免登录：令牌本身就是授权。只给服务对象需要知道的几件事。"""
    ratelimit.check(f"recipient-progress:{client_ip(request)}", VIEWS_PER_MINUTE, 60)
    row = db.query(RecipientLink).filter(RecipientLink.token_hash == _hash(token)).first()
    if row is None or row.revoked_at is not None:
        raise not_found("这条链接不对或已经被作废了：请找发单的家人重新发一条", "recipient_link_invalid")
    if row.expires_at <= utcnow():
        raise not_found("这条链接已经过期了：请找发单的家人重新发一条", "recipient_link_expired")
    task = db.get(Task, row.task_id)
    if task is None or not task.on_behalf:
        raise not_found("这条链接不对或已经被作废了：请找发单的家人重新发一条", "recipient_link_invalid")
    slots = db.query(Task).filter(Task.parent_id == task.id, Task.on_behalf.is_(True)).order_by(Task.id).all()
    units = slots or [task]
    ids = [t.id for t in units]
    users = {u.id: u for u in db.query(User).filter(User.id.in_([t.executor_id for t in units if t.executor_id]))}
    # work_date 是日期（北京时间的哪一天），没有时区可言：str(date) 就是 YYYY-MM-DD
    helpers = [{**_helper(users.get(t.executor_id)), "work_date": str(t.work_date) if t.work_date else None}
               for t in units if t.executor_id and t.status != "cancelled"]
    execs = {t.id: t.executor_id for t in units}
    logs = [lg for lg in db.query(ProgressLog).filter(ProgressLog.task_id.in_(ids), ProgressLog.kind.in_(("checkin", "visit")))
            if execs.get(lg.task_id) == lg.user_id]
    last = max((lg.created_at for lg in logs), default=None)
    row.view_count = (row.view_count or 0) + 1
    row.last_viewed_at = utcnow()
    phase = _phase(task, slots)
    return {
        "recipient_label": task.recipient_label, "title": task.title, "phase": phase, "phase_text": PHASE_TEXT[phase],
        "helpers": helpers,
        "work_date": str(task.work_date) if task.work_date else None, "days": task.days or 1,
        "shift_start": task.shift_start, "shift_end": task.shift_end,
        "deadline": iso(task.deadline) if task.deadline else None,
        "visits_planned": sum(t.visits_planned or 0 for t in units),
        "visits_reported": sum(1 for lg in logs if lg.kind == "visit"),
        "last_arrival_at": iso(last) if last else None,
        "expires_at": iso(row.expires_at),
    }


def purge_expired(db: Session, older_than_days: int = 30) -> int:
    """过期或作废满 30 天的链接记录物理删除（只剩哈希与计数，留着没有用处）。由 purge-locations 一起跑。"""
    cutoff = utcnow() - timedelta(days=older_than_days)
    return (db.query(RecipientLink)
            .filter((RecipientLink.expires_at <= cutoff) | (RecipientLink.revoked_at <= cutoff))
            .delete(synchronize_session=False))
