from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User
from app.modules.task.models import Task
from app.modules.task.router import dump_task

from . import service
from .llm import get_gateway
from .models import Decomposition

router = APIRouter(tags=["decompose"])


class ItemsIn(BaseModel):
    items: list[dict]


def _dump(d: Decomposition) -> dict:
    return {"id": d.id, "task_id": d.task_id, "items": d.items, "status": d.status, "source": d.source}


def _get_parent(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if task.creator_id != user.id:
        raise forbidden()
    return task


@router.post("/tasks/{task_id}/decompositions", status_code=201)
def propose(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-DEC-010 生成分解提案（草稿，不直接发布）。"""
    task = _get_parent(db, task_id, user)
    items = get_gateway().decompose(db, task.title, task.description, task.category, task.budget_cents)
    service.validate_items(items, task.budget_cents)
    row = Decomposition(
        task_id=task.id, creator_id=user.id, items=items,
        source=items[0].get("source", "") if items else "",
    )
    db.add(row)
    db.flush()
    return _dump(row)


@router.patch("/decompositions/{dec_id}")
def edit(dec_id: int, body: ItemsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-DEC-011 用户编辑分解草稿。"""
    row = db.get(Decomposition, dec_id)
    if not row:
        raise not_found("提案不存在")
    if row.creator_id != user.id:
        raise forbidden()
    parent = db.get(Task, row.task_id)
    service.validate_items(body.items, parent.budget_cents)
    row.items = body.items
    db.add(row)
    return _dump(row)


@router.post("/decompositions/{dec_id}/confirm")
def confirm(dec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """确认分解 → 生成子任务树，无依赖者自动发布（AI-DEC-020）。"""
    row = db.get(Decomposition, dec_id)
    if not row:
        raise not_found("提案不存在")
    if row.creator_id != user.id:
        raise forbidden()
    parent = db.get(Task, row.task_id)
    children = service.confirm(db, row, parent)
    return {"decomposition": _dump(row), "children": [dump_task(c, user) for c in children]}


@router.get("/tasks/{task_id}/tree")
def tree(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-DEC-021 母任务驾驶舱数据。"""
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    return service.tree_progress(db, task)
