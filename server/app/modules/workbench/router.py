"""PWB 个人工作台接口（116 号 spec）。全部只对本人可见：别人的资源一律 404，不泄露是否存在。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, conflict, not_found
from app.core.locks import job_slot
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import WbItem, WbLog, WbMemory, WbProject, WbRoutine, WbRoutineRun

router = APIRouter(tags=["workbench"])

Status = Literal["todo", "doing", "blocked", "done", "dropped"]


def _check_hhmm(v: str) -> str:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
        raise ValueError("时间格式为 HH:MM（北京时间）")
    return v


class _In(BaseModel):
    # 多收的字段（owner_id、reminded_at、completed_at……）直接 422：不让客户端改不该改的
    model_config = ConfigDict(extra="forbid")


class ProjectIn(_In):
    name: str = Field(min_length=1, max_length=60)
    color: Literal["clay", "moss", "ink", "sky", "sun"] = "clay"


class ProjectPatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: Literal["clay", "moss", "ink", "sky", "sun"] | None = None
    archived: bool | None = None
    sort: int | None = Field(default=None, ge=0, le=10000)


class ItemIn(_In):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=5000)
    project_id: int | None = None
    parent_id: int | None = None
    status: Status = "todo"
    priority: int = Field(default=1, ge=0, le=3)
    category: str = Field(default="", max_length=40)
    due_at: datetime | None = None
    remind_at: datetime | None = None
    progress: int = Field(default=0, ge=0, le=100)
    tags: list[str] = Field(default_factory=list, max_length=10)
    linked_task_id: int | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        return [t.strip()[:20] for t in v if t.strip()]


class ItemPatch(_In):
    revision: int | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=5000)
    project_id: int | None = None
    status: Status | None = None
    priority: int | None = Field(default=None, ge=0, le=3)
    category: str | None = Field(default=None, max_length=40)
    due_at: datetime | None = None
    remind_at: datetime | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = Field(default=None, max_length=10)
    linked_task_id: int | None = None
    sort: int | None = Field(default=None, ge=0, le=100000)


class LogIn(_In):
    body: str = Field(min_length=1, max_length=2000)


class StepIn(_In):
    title: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=500)


class ChildrenIn(_In):
    steps: list[StepIn] = Field(min_length=1, max_length=50)


class MemoryIn(_In):
    content: str = Field(min_length=1, max_length=200)


class RoutineIn(_In):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["digest", "review", "reminder"]
    freq: Literal["once", "daily", "weekly", "monthly"]
    time_of_day: str = "09:00"
    weekday: int = Field(default=0, ge=0, le=6)
    monthday: int = Field(default=1, ge=1, le=31)
    run_at: datetime | None = None
    note: str = Field(default="", max_length=500)
    item_id: int | None = None
    enabled: bool = True

    @field_validator("time_of_day")
    @classmethod
    def _hhmm(cls, v):
        return _check_hhmm(v)


class RoutinePatch(_In):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    freq: Literal["once", "daily", "weekly", "monthly"] | None = None
    time_of_day: str | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    monthday: int | None = Field(default=None, ge=1, le=31)
    run_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None

    @field_validator("time_of_day")
    @classmethod
    def _hhmm(cls, v):
        return v if v is None else _check_hhmm(v)


# ------------------------------------------------------------------ 工具
def _own(db: Session, model, obj_id: int, user: User, what: str):
    obj = db.get(model, obj_id)
    if obj is None or obj.owner_id != user.id:
        raise not_found(f"{what}不存在")
    return obj


def _limit(db: Session, model, user: User, key: str, *extra) -> None:
    if svc.count(db, model, user.id, *extra) >= svc.LIMITS[key]:
        raise conflict(f"数量已达上限（{svc.LIMITS[key]}），请先归档或删除不用的", "wb_limit_reached")


def _check_project(db: Session, project_id: int | None, user: User) -> None:
    if project_id is not None:
        _own(db, WbProject, project_id, user, "项目")


def _check_linked(db: Session, task_id: int | None, user: User) -> None:
    """只能关联自己发布或执行的平台任务：否则等于能窥探任意任务的状态。"""
    if task_id is None:
        return
    from app.modules.task.models import Task

    t = db.get(Task, task_id)
    if t is None or user.id not in (t.creator_id, t.executor_id):
        raise not_found("平台任务不存在或与你无关")


def _log(db: Session, item: WbItem, kind: str, body: str) -> None:
    db.add(WbLog(item_id=item.id, owner_id=item.owner_id, kind=kind, body=body))


def _dump_one(db: Session, item: WbItem) -> dict:
    return svc.dump_item(item, svc.ListCtx(db, [item]))


def _dump_project(p: WbProject) -> dict:
    return {"id": p.id, "name": p.name, "color": p.color, "archived": p.archived, "sort": p.sort,
            "created_at": iso(p.created_at)}


def _dump_routine(r: WbRoutine) -> dict:
    return {"id": r.id, "name": r.name, "kind": r.kind, "freq": r.freq, "time_of_day": r.time_of_day,
            "weekday": r.weekday, "monthday": r.monthday, "run_at": iso(r.run_at), "note": r.note,
            "item_id": r.item_id, "enabled": r.enabled, "next_run_at": iso(r.next_run_at),
            "last_run_at": iso(r.last_run_at), "last_status": r.last_status, "failures": r.failures}


# ------------------------------------------------------------------ 项目
@router.get("/workbench/projects")
def list_projects(include_archived: bool = False, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    q = db.query(WbProject).filter(WbProject.owner_id == user.id)
    if not include_archived:
        q = q.filter(WbProject.archived.is_(False))
    return [_dump_project(p) for p in q.order_by(WbProject.sort, WbProject.id).all()]


@router.post("/workbench/projects", status_code=201)
def create_project(body: ProjectIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    _limit(db, WbProject, user, "projects")
    p = WbProject(owner_id=user.id, name=body.name.strip(), color=body.color)
    db.add(p)
    db.flush()
    return _dump_project(p)


@router.patch("/workbench/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    p = _own(db, WbProject, project_id, user, "项目")
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    db.add(p)
    db.flush()
    return _dump_project(p)


@router.delete("/workbench/projects/{project_id}")
def delete_project(project_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    p = _own(db, WbProject, project_id, user, "项目")
    if db.query(WbItem.id).filter(WbItem.project_id == p.id).first():
        raise conflict("项目里还有任务：可以先归档项目，或把任务移走后再删", "project_not_empty")
    db.delete(p)
    return {"deleted": True}


# ------------------------------------------------------------------ 任务
@router.get("/workbench/items")
def list_items(project_id: int | None = None, status: Status | None = None,
               view: Literal["all", "today", "overdue", "week", "open"] = "all",
               q: str = Query(default="", max_length=60), limit: int = Query(default=200, ge=1, le=500),
               user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """顶层任务（清单子项随任务详情返回）。`view`：今天 / 已逾期 / 本周 / 未完成 / 全部。"""
    qy = db.query(WbItem).filter(WbItem.owner_id == user.id, WbItem.parent_id.is_(None))
    if project_id is not None:
        qy = qy.filter(WbItem.project_id == project_id)
    if status is not None:
        qy = qy.filter(WbItem.status == status)
    now = utcnow()
    if view != "all":
        qy = qy.filter(WbItem.status.in_(svc.OPEN))
        loc = svc.local(now)
        if view == "today":
            end = svc._back(loc.replace(hour=23, minute=59, second=59, microsecond=0))
            qy = qy.filter(WbItem.due_at.isnot(None), WbItem.due_at <= end)
        elif view == "overdue":
            qy = qy.filter(WbItem.due_at.isnot(None), WbItem.due_at < now)
        elif view == "week":
            end = svc._back((loc + timedelta(days=6 - loc.weekday())).replace(hour=23, minute=59, second=59))
            qy = qy.filter(WbItem.due_at.isnot(None), WbItem.due_at <= end)
    if q.strip():
        like = f"%{q.strip()}%"
        qy = qy.filter(or_(WbItem.title.like(like), WbItem.notes.like(like)))
    rows = qy.order_by(WbItem.status == "done", WbItem.due_at.is_(None), WbItem.due_at,
                       WbItem.priority.desc(), WbItem.sort, WbItem.id.desc()).limit(limit).all()
    ctx = svc.ListCtx(db, rows)
    return [svc.dump_item(i, ctx) for i in rows]


@router.post("/workbench/items", status_code=201)
def create_item(body: ItemIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    _limit(db, WbItem, user, "items")
    _check_project(db, body.project_id, user)
    _check_linked(db, body.linked_task_id, user)
    project_id = body.project_id
    if body.parent_id is not None:
        parent = _own(db, WbItem, body.parent_id, user, "任务")
        if parent.parent_id is not None:
            raise conflict("清单只有一层：子项下面不能再加子项", "only_one_level")
        if db.query(WbItem).filter(WbItem.parent_id == parent.id).count() >= svc.LIMITS["children"]:
            raise conflict(f"一个任务最多 {svc.LIMITS['children']} 个子项", "wb_limit_reached")
        project_id = parent.project_id
    now = utcnow()
    item = WbItem(owner_id=user.id, project_id=project_id, parent_id=body.parent_id, title=body.title.strip(),
                  notes=body.notes, status=body.status, priority=body.priority, category=body.category,
                  due_at=svc.to_utc(body.due_at), remind_at=svc.to_utc(body.remind_at), progress=body.progress,
                  tags=body.tags, linked_task_id=body.linked_task_id, created_at=now, updated_at=now,
                  completed_at=now if body.status == "done" else None)
    db.add(item)
    db.flush()
    return _dump_one(db, item)


@router.get("/workbench/items/{item_id}")
def get_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    children = db.query(WbItem).filter(WbItem.parent_id == item.id).order_by(WbItem.sort, WbItem.id).all()
    cctx = svc.ListCtx(db, children)
    return {**_dump_one(db, item), "children": [svc.dump_item(c, cctx) for c in children]}


@router.patch("/workbench/items/{item_id}")
def update_item(item_id: int, body: ItemPatch, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    if body.revision is not None and body.revision != item.revision:
        raise conflict("这个任务已在其他窗口或设备上改过，请刷新后再改", "wb_revision_conflict")
    data = body.model_dump(exclude_unset=True)
    data.pop("revision", None)
    if "project_id" in data:
        _check_project(db, data["project_id"], user)
    if "linked_task_id" in data:
        _check_linked(db, data["linked_task_id"], user)
    if "progress" in data and data["progress"] is not None:
        if db.query(WbItem.id).filter(WbItem.parent_id == item.id).first():
            raise conflict("这个任务的进度按清单子项自动计算，不能手填", "progress_from_children")
        if data.get("linked_task_id", item.linked_task_id):
            raise conflict("关联了平台任务，进度跟着平台任务走，不能手填", "progress_from_platform")
    now = utcnow()
    old_status, old_progress = item.status, item.progress
    for k in ("title", "notes", "priority", "category", "tags", "sort"):
        if data.get(k) is not None:
            setattr(item, k, data[k].strip() if k == "title" else data[k])
    for k in ("project_id", "linked_task_id"):
        if k in data:
            setattr(item, k, data[k])
    for k in ("due_at", "remind_at"):
        if k in data:
            setattr(item, k, svc.to_utc(data[k]))
    if "remind_at" in data:
        item.reminded_at = None      # 改了提醒时间就重新提醒
    if data.get("status") and data["status"] != old_status:
        item.status = data["status"]
        item.completed_at = now if item.status == "done" else None
        _log(db, item, "status", f"{svc.STATUS_NAMES[old_status]} → {svc.STATUS_NAMES[item.status]}")
    if data.get("progress") is not None and data["progress"] != old_progress:
        item.progress = data["progress"]
        _log(db, item, "progress", f"进度 {old_progress}% → {item.progress}%")
    item.updated_at = now
    item.revision += 1
    db.add(item)
    db.flush()
    return _dump_one(db, item)


@router.delete("/workbench/items/{item_id}")
def delete_item(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    ids = [item.id] + [i for (i,) in db.query(WbItem.id).filter(WbItem.parent_id == item.id)]
    db.query(WbLog).filter(WbLog.item_id.in_(ids)).delete(synchronize_session=False)
    db.query(WbItem).filter(WbItem.parent_id == item.id).delete(synchronize_session=False)
    db.query(WbRoutine).filter(WbRoutine.item_id.in_(ids)).update({"item_id": None}, synchronize_session=False)
    db.delete(item)
    return {"deleted": True}


@router.get("/workbench/items/{item_id}/logs")
def list_logs(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    rows = db.query(WbLog).filter(WbLog.item_id == item.id).order_by(WbLog.id.desc()).limit(200).all()
    return [{"id": r.id, "kind": r.kind, "body": r.body, "created_at": iso(r.created_at)} for r in rows]


@router.post("/workbench/items/{item_id}/logs", status_code=201)
def add_log(item_id: int, body: LogIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    if db.query(WbLog).filter(WbLog.item_id == item.id).count() >= svc.LIMITS["logs"]:
        raise conflict(f"一个任务最多 {svc.LIMITS['logs']} 条进展记录", "wb_limit_reached")
    row = WbLog(item_id=item.id, owner_id=user.id, kind="note", body=body.body.strip())
    db.add(row)
    item.updated_at = utcnow()     # 写了进展就不算「没动静」
    db.add(item)
    db.flush()
    return {"id": row.id, "kind": row.kind, "body": row.body, "created_at": iso(row.created_at)}


@router.post("/workbench/items/{item_id}/breakdown")
def breakdown(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """助手拆清单：**只返回草稿**，不写库。确认后调 `/children`。"""
    item = _own(db, WbItem, item_id, user, "任务")
    if item.parent_id is not None:
        raise conflict("清单只有一层：子项不能再拆", "only_one_level")
    return svc.breakdown(db, item)


@router.post("/workbench/items/{item_id}/children", status_code=201)
def add_children(item_id: int, body: ChildrenIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")):
    item = _own(db, WbItem, item_id, user, "任务")
    if item.parent_id is not None:
        raise conflict("清单只有一层：子项下面不能再加子项", "only_one_level")
    have = db.query(WbItem).filter(WbItem.parent_id == item.id).count()
    if have + len(body.steps) > svc.LIMITS["children"]:
        raise conflict(f"一个任务最多 {svc.LIMITS['children']} 个子项", "wb_limit_reached")
    if svc.count(db, WbItem, user.id) + len(body.steps) > svc.LIMITS["items"]:
        raise conflict(f"数量已达上限（{svc.LIMITS['items']}），请先归档或删除不用的", "wb_limit_reached")
    now = utcnow()
    for n, s in enumerate(body.steps):
        db.add(WbItem(owner_id=user.id, project_id=item.project_id, parent_id=item.id, title=s.title.strip(),
                      notes=s.note, sort=have + n, created_at=now, updated_at=now))
    _log(db, item, "assistant", f"加入清单 {len(body.steps)} 项")
    item.updated_at = now
    db.add(item)
    db.flush()
    return get_item(item.id, user, db)


@router.get("/workbench/overview")
def get_overview(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    ov = svc.overview(db, user.id)
    return {**ov, "summary": svc.digest_text(ov)}


# ------------------------------------------------------------------ 助手记忆
@router.get("/workbench/memories")
def list_memories(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(WbMemory).filter(WbMemory.owner_id == user.id).order_by(WbMemory.id).all()
    return {"limit": svc.LIMITS["memories"],
            "items": [{"id": m.id, "content": m.content, "created_at": iso(m.created_at)} for m in rows]}


@router.post("/workbench/memories", status_code=201)
def add_memory(body: MemoryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    _limit(db, WbMemory, user, "memories")
    m = WbMemory(owner_id=user.id, content=body.content.strip())
    db.add(m)
    db.flush()
    return {"id": m.id, "content": m.content, "created_at": iso(m.created_at)}


@router.delete("/workbench/memories/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    db.delete(_own(db, WbMemory, memory_id, user, "记忆"))
    return {"deleted": True}


# ------------------------------------------------------------------ 例行任务
def _schedule(r: WbRoutine) -> None:
    if r.freq == "once" and r.run_at is None:
        raise bad_request("一次性的例行任务要给出运行时间", "routine_needs_time")
    r.next_run_at = svc.next_run(r, utcnow()) if r.enabled else None
    if r.enabled and r.next_run_at is None:
        raise bad_request("运行时间已经过去了", "routine_time_passed")


@router.get("/workbench/routines")
def list_routines(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(WbRoutine).filter(WbRoutine.owner_id == user.id).order_by(WbRoutine.id).all()
    return [_dump_routine(r) for r in rows]


@router.post("/workbench/routines", status_code=201)
def create_routine(body: RoutineIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    _limit(db, WbRoutine, user, "routines")
    if body.item_id is not None:
        _own(db, WbItem, body.item_id, user, "任务")
    r = WbRoutine(owner_id=user.id, **body.model_dump(exclude={"run_at"}), run_at=svc.to_utc(body.run_at))
    _schedule(r)
    db.add(r)
    db.flush()
    return _dump_routine(r)


@router.patch("/workbench/routines/{routine_id}")
def update_routine(routine_id: int, body: RoutinePatch, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    r = _own(db, WbRoutine, routine_id, user, "例行任务")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if v is not None or k == "run_at":
            setattr(r, k, svc.to_utc(v) if k == "run_at" else v)
    if data.get("enabled"):
        r.failures = 0       # 重新开启＝人看过了，失败计数从头算
    _schedule(r)
    db.add(r)
    db.flush()
    return _dump_routine(r)


@router.delete("/workbench/routines/{routine_id}")
def delete_routine(routine_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    r = _own(db, WbRoutine, routine_id, user, "例行任务")
    db.query(WbRoutineRun).filter(WbRoutineRun.routine_id == r.id).delete(synchronize_session=False)
    db.delete(r)
    return {"deleted": True}


@router.post("/workbench/routines/{routine_id}/run")
def run_now(routine_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """立即运行一次（试运行）：不改下一次的排期。"""
    r = _own(db, WbRoutine, routine_id, user, "例行任务")
    run = svc.run_routine(db, r, utcnow(), manual=True)
    db.flush()
    return {"status": run.status, "output": run.output, "routine": _dump_routine(r)}


@router.get("/workbench/routines/{routine_id}/runs")
def list_runs(routine_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    r = _own(db, WbRoutine, routine_id, user, "例行任务")
    rows = db.query(WbRoutineRun).filter(WbRoutineRun.routine_id == r.id).order_by(WbRoutineRun.id.desc()).limit(50)
    return [{"id": x.id, "status": x.status, "output": x.output, "started_at": iso(x.started_at)} for x in rows]


@router.post("/workbench/jobs/run-routines")
def job_run_routines(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                     __=Depends(job_slot("wb_routines"), scope="function")):
    return svc.run_due(db)
