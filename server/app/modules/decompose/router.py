from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.task.models import Task
from app.modules.task.router import dump_task

from . import service
from . import tree as tree_ops
from .llm import get_gateway
from .models import Decomposition

router = APIRouter(tags=["decompose"])


class ItemsIn(BaseModel):
    items: list[dict]


def _dump(d: Decomposition) -> dict:
    """V132 起多了整棵树（`nodes`）；`items` 对树形提案是第一层的只读视图，
    老客户端照样能读。"""
    if not d.tree:
        return {"id": d.id, "task_id": d.task_id, "items": d.items, "status": d.status,
                "source": d.source, "mode": "flat", "nodes": [], "revision": d.revision,
                "unresolved": [], "can_expand": False, "fallback": False, "model_calls": 0}
    nodes = [{**n, "stop_note": tree_ops.STOP_NOTES.get(n["stop_reason"], "")} for n in d.tree]
    return {
        "id": d.id, "task_id": d.task_id, "items": tree_ops.items_view(d.tree),
        "status": d.status, "source": d.source, "mode": "tree", "nodes": nodes,
        "revision": d.revision,
        # 确认前必须说清的步骤：服务端判断，界面照着显示
        "unresolved": tree_ops.unresolved(d.tree),
        "can_expand": d.status == "proposed" and bool(tree_ops.frontier(d.tree)),
        # AI-DEC-048 回落模板必须看得见
        "fallback": any(n.get("fallback") for n in d.tree),
        "model_calls": d.model_calls,
    }


def _get_dec(db: Session, dec_id: int, user: User) -> Decomposition:
    row = db.get(Decomposition, dec_id)
    if not row:
        raise not_found("提案不存在")
    if row.creator_id != user.id:
        raise forbidden()
    return row


def _save(db: Session, row: Decomposition, expected: int, nodes: list[dict],
          model_calls: int | None = None) -> None:
    """比较并交换：读到的 revision 还是库里的，才写回整棵树。

    逐层展开与逐点编辑都是「读整棵树 → 改 → 写回」；两个窗口同时改，后写的会把
    先写的整个覆盖掉，而用户不会知道自己刚才的修改丢了。
    """
    values = {"tree": nodes, "revision": expected + 1}
    if model_calls is not None:
        values["model_calls"] = model_calls
    n = (db.query(Decomposition)
         .filter(Decomposition.id == row.id, Decomposition.revision == expected)
         .update(values, synchronize_session=False))
    if n != 1:
        raise conflict("这份拆解刚被另一个窗口改过，请刷新后再改", "decomposition_changed")
    db.refresh(row)


def _editable(row: Decomposition, revision: int | None) -> int:
    if row.status != "proposed":
        raise conflict("提案已处理", "not_proposed")
    if not row.tree:
        raise conflict("这是逐层拆解之前的提案，不能逐步编辑", "not_a_tree")
    if revision is not None and revision != row.revision:
        raise conflict("这份拆解刚被另一个窗口改过，请刷新后再改", "decomposition_changed")
    return row.revision


def _get_parent(db: Session, task_id: int, user: User) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if task.creator_id != user.id:
        raise forbidden()
    return task


@router.post("/tasks/{task_id}/decompositions", status_code=201)
def propose(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AI-DEC-010 生成分解提案（草稿，不直接发布）。

    V132 起是**树的第一层**（AI-DEC-041）：之后每调一次 `/expand` 往下长一层，
    每一层都落盘、都能改。
    """
    task = _get_parent(db, task_id, user)
    nodes, calls, report = tree_ops.expand(db, task, [], None, get_gateway(), 0)
    tree_ops.validate_tree(nodes, task.budget_cents)
    row = Decomposition(task_id=task.id, creator_id=user.id, items=[], tree=nodes,
                        model_calls=calls, source=nodes[0]["source"] if nodes else "")
    db.add(row)
    db.flush()
    tree_ops.record_unit_uses(db, task, report)
    return _dump(row)


@router.get("/tasks/{task_id}/decomposition")
def current_proposal(task_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db, scope="function")):
    """拆到一半关掉页面，回来接着拆：这个任务最近一份还没确认的提案（仅发布方）。

    逐层展开的意义在于能停、能改、能接着来（AI-DEC-041）；读不回来的草稿只能重来。
    """
    task = _get_parent(db, task_id, user)
    row = (db.query(Decomposition)
           .filter(Decomposition.task_id == task.id, Decomposition.status == "proposed")
           .order_by(Decomposition.id.desc()).first())
    if not row:
        raise not_found("这个任务没有进行中的拆解", "no_decomposition_in_progress")
    return _dump(row)


class ExpandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int
    # 不给：展开整个前沿（下一层）；给：只拆这几步（用户点了「拆这一步」）
    node_ids: list[int] | None = None


@router.post("/decompositions/{dec_id}/expand")
def expand(dec_id: int, body: ExpandIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db, scope="function")):
    """AI-DEC-041 往下长一层（或只拆指定的几步）。可见、可打断：一次一层，每层落盘。"""
    row = _get_dec(db, dec_id, user)
    rev = _editable(row, body.revision)
    task = db.get(Task, row.task_id)
    nodes, calls, report = tree_ops.expand(db, task, row.tree, body.node_ids, get_gateway(),
                                       row.model_calls)
    tree_ops.validate_tree(nodes, task.budget_cents)
    _save(db, row, rev, nodes, calls)
    tree_ops.record_unit_uses(db, task, report)
    report.pop("unit_uses", None)  # 内部记账用，不是响应的一部分
    return {**_dump(row), "report": report}


class NodePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    budget_cents: int | None = Field(default=None, gt=0)
    deliverable: str | None = Field(default=None, max_length=300)
    acceptance: str | None = Field(default=None, max_length=500)
    single_owner: bool | None = None
    category: str | None = Field(default=None, max_length=50)
    executor_hint: str | None = None
    depends_on: list[int] | None = None


@router.patch("/decompositions/{dec_id}/nodes/{node_id}")
def edit_node(dec_id: int, node_id: int, body: NodePatchIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")):
    """AI-DEC-011 逐步编辑：补交付物与验收标准、改预算、说清谁来做（AI-DEC-044）。"""
    row = _get_dec(db, dec_id, user)
    rev = _editable(row, body.revision)
    task = db.get(Task, row.task_id)
    patch = body.model_dump(exclude_none=True, exclude={"revision"})
    if not patch:
        raise bad_request("没有要改的内容", "empty_patch")
    nodes = tree_ops.edit_node(db, task, row.tree, node_id, patch)
    _save(db, row, rev, nodes)
    return _dump(row)


@router.delete("/decompositions/{dec_id}/nodes/{node_id}")
def delete_node(dec_id: int, node_id: int, revision: int = Query(...),
                user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """删掉一步（连同它下面的步骤）。"""
    row = _get_dec(db, dec_id, user)
    rev = _editable(row, revision)
    task = db.get(Task, row.task_id)
    nodes = tree_ops.delete_node(row.tree, node_id, db, task)
    tree_ops.validate_tree(nodes, task.budget_cents)
    _save(db, row, rev, nodes)
    return _dump(row)


@router.patch("/decompositions/{dec_id}")
def edit(dec_id: int, body: ItemsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AI-DEC-011 用户编辑分解草稿（一层的写法；树只有一层时也能用）。"""
    row = _get_dec(db, dec_id, user)
    parent = db.get(Task, row.task_id)
    if row.tree:
        if row.status != "proposed":
            raise conflict("提案已处理", "not_proposed")
        _save(db, row, row.revision, tree_ops.nodes_from_items(db, parent, row.tree, body.items))
        return _dump(row)
    service.validate_items(body.items, parent.budget_cents)
    row.items = body.items
    db.add(row)
    return _dump(row)


@router.post("/decompositions/{dec_id}/confirm")
def confirm(dec_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """确认分解 → 生成子任务树，无依赖者自动发布（AI-DEC-020）。

    树形提案：每个没有子步骤的节点都必须是叶子且说清了谁来做，否则 409 并列出是哪几步
    （AI-DEC-044：每一种判定都要有去处，「判不了」的去处是让人选）。
    """
    row = _get_dec(db, dec_id, user)
    parent = db.get(Task, row.task_id)
    if row.tree:
        if row.status != "proposed":
            raise conflict("提案已处理", "not_proposed")
        nodes, tasks = tree_ops.confirm(db, row.tree, parent)
        _save(db, row, row.revision, nodes)
        row.status = "confirmed"
        db.add(row)
        return {"decomposition": _dump(row), "children": [dump_task(c, user) for c in tasks]}
    children = service.confirm(db, row, parent)
    return {"decomposition": _dump(row), "children": [dump_task(c, user) for c in children]}


@router.get("/tasks/{task_id}/tree")
def tree(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AI-DEC-021 母任务驾驶舱数据。"""
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    return service.tree_progress(db, task)


@router.get("/tasks/{task_id}/final-report")
def final_report(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
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
def clarify(body: ClarifyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
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
