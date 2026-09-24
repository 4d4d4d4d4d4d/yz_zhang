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


@router.get("/tasks/{task_id}/final-report")
def final_report(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-DEC-025 结项报告：成本/工期/交付清单汇总（仅发布者）。"""
    parent = _get_parent(db, task_id, user)
    children = db.query(Task).filter(Task.parent_id == parent.id).order_by(Task.id).all()
    if not children:
        raise not_found("该任务没有子任务")
    completed = [c for c in children if c.status == "completed"]
    total_cost = sum(c.budget_cents for c in completed)
    duration_days = 0
    if parent.completed_at and parent.created_at:
        duration_days = max((parent.completed_at - parent.created_at).days, 0)
    return {
        "task_id": parent.id,
        "title": parent.title,
        "status": parent.status,
        "total_cost_cents": total_cost,
        "planned_budget_cents": parent.budget_cents,
        "duration_days": duration_days,
        "children_total": len(children),
        "children_completed": len(completed),
        "deliverables": [
            {"task_id": c.id, "title": c.title, "executor_id": c.executor_id,
             "cost_cents": c.budget_cents, "status": c.status}
            for c in children
        ],
        "summary": (
            f"共 {len(children)} 个子任务，完成 {len(completed)} 个，"
            f"实际支出 {total_cost / 100:.2f} 元"
            f"（计划预算 {parent.budget_cents / 100:.2f} 元）"
        ),
    }


class ClarifyIn(BaseModel):
    title: str = ""
    description: str = ""
    category: str = ""
    budget_cents: int | None = None
    city: str = ""
    is_remote: bool | None = None


@router.post("/ai/clarify")
def clarify(body: ClarifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """AI-DEC-001 对话式需求澄清 + AI-DEC-002 可行性预判。

    规则驱动的澄清器（生产由 LLM 网关生成追问，结构不变）：
    返回缺失要素的追问列表 + 基于知识库的预算可行性提示。
    """
    questions = []
    if not body.title or len(body.title) < 2:
        questions.append({"field": "title", "question": "想让别人帮你做什么？用一句话概括"})
    if not body.category:
        questions.append({"field": "category", "question": "任务属于哪个类目（如保洁/跑腿/软件开发）？"})
    if not body.budget_cents:
        questions.append({"field": "budget_cents", "question": "预算大约多少元？"})
    if body.is_remote is None:
        questions.append({"field": "is_remote", "question": "需要线下上门，还是线上远程完成？"})
    elif not body.is_remote and not body.city:
        questions.append({"field": "city", "question": "任务地点在哪个城市？"})
    if not body.description:
        questions.append({"field": "description", "question": "有什么具体要求或验收标准？"})

    feasibility = None
    if body.category and body.budget_cents:
        from app.modules.knowledge import service as kb

        ref = kb.price_reference(db, body.category, body.city or None)
        if ref["sample_size"] > 0:
            p50 = ref["p50_cents"]
            if body.budget_cents < p50 * 6 // 10:
                feasibility = {"level": "low_budget", "p50_cents": p50,
                               "message": f"预算低于同类闭环任务中位价（{p50 / 100:.0f} 元）的 60%，可能难以招募"}
            elif body.budget_cents > p50 * 2:
                feasibility = {"level": "over_budget", "p50_cents": p50,
                               "message": f"预算高于中位价（{p50 / 100:.0f} 元）2 倍，可适当下调"}
            else:
                feasibility = {"level": "ok", "p50_cents": p50, "message": "预算在合理区间"}
        else:
            feasibility = {"level": "no_data", "message": "暂无同类数据，建议参考平台模板"}

    return {"ready": not questions, "questions": questions, "feasibility": feasibility}
