"""AI-DEC-024（321 号 spec）跨子任务产出共享：前一步的交付人授权后，后一步的执行者才看得到。

一个项目拆成几步，后一步常常要前一步的成果（设计稿给开发、测量数据给施工），以前只能私下传。
可前一个人的交付物给不给后一个人看，是他的权利，不是流程的便利，所以：
- 默认谁也看不到；只有前一步的执行者（交付人）能开，开给依赖它的那一步（同一个项目下、depends_on 里有它）；
- 交了才能开（还没交付，没有东西可给）；随时可以收回，收回后立刻看不到；
- 开放的是交付说明与预览图；原图放款后归发单人（知识产权约定），交付人开不了，要发单人另行决定（AI-DEC-024b）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from .models import ProgressLog, SubtaskShare, Task

router = APIRouter(tags=["task"])


class ShareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_task_id: int = Field(ge=1)


def _task(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None:
        raise not_found("任务不存在")
    return t


def _next_steps(db: Session, t: Task) -> list[Task]:
    """依赖这一步的兄弟任务（同一个母任务下、depends_on 里有它）。"""
    if t.parent_id is None:
        return []
    sibs = db.query(Task).filter(Task.parent_id == t.parent_id, Task.id != t.id).order_by(Task.id).all()
    return [s for s in sibs if t.id in (s.depends_on or [])]


def _active(db: Session, from_id: int, to_id: int) -> SubtaskShare | None:
    return (db.query(SubtaskShare).filter(SubtaskShare.from_task_id == from_id, SubtaskShare.to_task_id == to_id,
                                          SubtaskShare.revoked_at.is_(None)).first())


def _view(db: Session, t: Task) -> dict:
    rows = []
    for s in _next_steps(db, t):
        ex = db.get(User, s.executor_id) if s.executor_id else None
        share = _active(db, t.id, s.id)
        row = {"task_id": s.id, "title": s.title, "status": s.status,
               "executor_nickname": ex.nickname if ex else None, "shared": share is not None}
        if share is not None:
            row["share_id"] = share.id
        rows.append(row)
    return {"task_id": t.id, "delivered": t.delivered_at is not None, "next_steps": rows}


@router.get("/tasks/{task_id}/shares")
def list_shares(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """前一步的交付人（与发单人）看：依赖这一步的有哪几步、现在是谁在做、开没开给他。"""
    t = _task(db, task_id)
    if user.id not in (t.executor_id, t.creator_id):
        raise forbidden("只有这一步的执行者和发单人看得到")
    return _view(db, t)


@router.post("/tasks/{task_id}/shares")
def grant_share(task_id: int, body: ShareIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    from app.modules.notification.service import notify

    t = _task(db, task_id)
    if user.id != t.executor_id:
        raise forbidden("开不开放成果是交付人的事：只有这一步的执行者能开")
    to = db.get(Task, body.to_task_id)
    if to is None or to not in _next_steps(db, t):
        raise bad_request("只能开给依赖这一步的那几步（同一个项目下、写明要等这一步的）", "share_not_next_step")
    if t.delivered_at is None:
        raise conflict("这一步还没交付：交了之后再开放给下一步", "not_delivered")
    if _active(db, t.id, to.id) is None:
        db.add(SubtaskShare(from_task_id=t.id, to_task_id=to.id, granted_by=user.id))
        db.flush()
        if to.executor_id:
            notify(db, to.executor_id, "task", f"前一步「{t.title}」的成果开放给你了",
                   f"在「{to.title}」的任务页「前一步的成果」里看交付说明与预览图；交付人可以随时收回。")
    return _view(db, t)


@router.delete("/tasks/{task_id}/shares/{share_id}")
def revoke_share(task_id: int, share_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")):
    from app.modules.notification.service import notify

    t = _task(db, task_id)
    if user.id != t.executor_id:
        raise forbidden("只有这一步的执行者能收回")
    share = db.get(SubtaskShare, share_id)
    if share is None or share.from_task_id != t.id or share.revoked_at is not None:
        raise not_found("没有这条开放记录（可能已经收回了）")
    share.revoked_at = utcnow()
    db.add(share)
    to = db.get(Task, share.to_task_id)
    if to is not None and to.executor_id:
        notify(db, to.executor_id, "task", f"前一步「{t.title}」的成果已收回",
               "交付人收回了开放；还需要的话，在项目里请发单人协调。")
    return _view(db, t)


@router.get("/tasks/{task_id}/inputs")
def task_inputs(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """后一步的执行者（与发单人）看：前一步的交付人开放给这一步的成果（交付说明与预览图）。"""
    from app.modules.contract.models import Contract, ContractDeliverable

    t = _task(db, task_id)
    if user.id not in (t.executor_id, t.creator_id):
        raise forbidden("只有这一步的执行者和发单人看得到")
    shares = (db.query(SubtaskShare).filter(SubtaskShare.to_task_id == t.id, SubtaskShare.revoked_at.is_(None))
              .order_by(SubtaskShare.id).all())
    out = []
    for s in shares:
        src = db.get(Task, s.from_task_id)
        if src is None:
            continue
        logs = (db.query(ProgressLog).filter(ProgressLog.task_id == src.id, ProgressLog.kind == "delivery")
                .order_by(ProgressLog.id).all())
        c = db.query(Contract).filter(Contract.task_id == src.id).order_by(Contract.id.desc()).first()
        previews = ([] if c is None else
                    db.query(ContractDeliverable).filter(ContractDeliverable.contract_id == c.id,
                                                         ContractDeliverable.kind == "preview")
                    .order_by(ContractDeliverable.id).all())
        out.append({"from_task_id": src.id, "title": src.title, "shared_at": iso(s.created_at),
                    "deliveries": [{"content": g.content, "images": list(g.images or []), "created_at": iso(g.created_at)}
                                   for g in logs],
                    "previews": [{"id": d.id, "url": f"/api/v1/files/{d.file_name}"} for d in previews]})
    return out
