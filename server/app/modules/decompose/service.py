"""分解确认与编排（AI-DEC-020/023, TASK-036）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.core.events import subscribe
from app.core.timefmt import day
from app.modules.task import service as task_service
from app.modules.task.models import Task

from .models import Decomposition


def validate_items(items: list[dict], parent_budget: int) -> None:
    """04.E 结构化输出校验：预算守恒 + DAG 无环。"""
    if not items:
        raise bad_request("子任务列表为空", "empty_items")
    total = sum(i.get("budget_cents", 0) for i in items)
    if total > parent_budget:
        raise bad_request(
            f"子任务预算合计 {total} 超出母任务预算 {parent_budget}", "budget_exceeded"
        )
    n = len(items)
    graph = {i: [d for d in (items[i].get("depends_on_idx") or [])] for i in range(n)}
    for i, deps in graph.items():
        if any(d < 0 or d >= n or d == i for d in deps):
            raise bad_request("依赖索引非法", "invalid_dependency")
    # 拓扑检测环
    state = [0] * n

    def dfs(u):
        state[u] = 1
        for v in graph[u]:
            if state[v] == 1 or (state[v] == 0 and dfs(v)):
                return True
        state[u] = 2
        return False

    if any(state[i] == 0 and dfs(i) for i in range(n)):
        raise bad_request("子任务依赖存在环", "cyclic_dependency")


def confirm(db: Session, decomposition: Decomposition, parent: Task) -> list[Task]:
    """AI-DEC-011 用户确认 → 生成子任务；AI-DEC-020 无前置依赖的先发布。"""
    if decomposition.status != "proposed":
        raise conflict("提案已处理", "not_proposed")
    validate_items(decomposition.items, parent.budget_cents)
    children: list[Task] = []
    for item in decomposition.items:
        child = Task(
            creator_id=parent.creator_id,
            parent_id=parent.id,
            title=item["title"],
            description=item.get("description", ""),
            category=parent.category,
            task_type=parent.task_type,
            required_skills=item.get("required_skills", []),
            budget_cents=item["budget_cents"],
            is_remote=parent.is_remote,
            city=parent.city,
            lat=parent.lat,
            lng=parent.lng,
            address_hint=parent.address_hint,
            address_exact=parent.address_exact,
        )
        db.add(child)
        children.append(child)
    db.flush()
    # depends_on 索引 → 实际任务 id
    for i, item in enumerate(decomposition.items):
        children[i].depends_on = [children[d].id for d in (item.get("depends_on_idx") or [])]
        db.add(children[i])
    # 无前置依赖的子任务立即发布
    for child in children:
        if not child.depends_on:
            task_service.transition(db, child, "published")
    decomposition.status = "confirmed"
    db.add(decomposition)
    return children


def tree_progress(db: Session, parent: Task) -> dict:
    """TASK-036/AI-DEC-021 母任务进度聚合（按预算加权）。"""
    children = db.query(Task).filter(Task.parent_id == parent.id).order_by(Task.id).all()
    total_budget = sum(c.budget_cents for c in children) or 1
    done_budget = sum(c.budget_cents for c in children if c.status == "completed")
    return {
        "parent_id": parent.id,
        "parent_status": parent.status,
        "progress_pct": round(done_budget * 100 / total_budget, 1) if children else 0,
        "children": [
            {
                "id": c.id, "title": c.title, "status": c.status,
                "budget_cents": c.budget_cents, "depends_on": c.depends_on,
                "executor_id": c.executor_id,
                # SCN-116（174 号 spec）：多天名额是哪一天的
                "work_date": day(c.work_date) if c.work_date else None,
            }
            for c in children
        ],
        "all_children_completed": bool(children) and all(c.status == "completed" for c in children),
        "by_day": by_day(children),
    }


# 名额「还缺人」：仍在招募且没人接；「已招到」：有人接了且没取消；取消的（含到期没人接被下架的）单独数，不算缺也不算招到
def by_day(children: list[Task]) -> list[dict]:
    """SCN-116 多天名额按天汇总（174 号 spec）：哪天几个名额、招到几个、还缺几个、做完几个。

    只看带日期的名额；没有日期的子任务（单天多人、项目拆解的步骤）不进来，返回空表——客户端照旧只画一排子任务。"""
    days: dict = {}
    for c in children:
        if not c.work_date:
            continue
        d = days.setdefault(c.work_date, {"date": day(c.work_date), "slots": 0, "filled": 0, "open": 0,
                                          "done": 0, "closed": 0})
        d["slots"] += 1
        if c.status == "completed":
            d["done"] += 1
        if c.executor_id is not None and c.status != "cancelled":
            d["filled"] += 1
        elif c.status == "published":
            d["open"] += 1
        else:
            d["closed"] += 1
    return [days[k] for k in sorted(days)]


# ---------- 事件：子任务完成 → 自动发布后继（AI-DEC-020） ----------
def _on_task_completed(db: Session, payload: dict) -> None:
    done = db.get(Task, payload["task_id"])
    if not done or not done.parent_id:
        return
    siblings = db.query(Task).filter(Task.parent_id == done.parent_id).all()
    status_map = {s.id: s.status for s in siblings}
    for sib in siblings:
        if sib.status == "draft" and sib.depends_on and all(
            status_map.get(dep) == "completed" for dep in sib.depends_on
        ):
            # AI-DEC-046 树形拆解里，后继可能是一个容器步骤（中间层）：
            # 它自己不发布、不托管，发布的是它下面没有前置的叶子
            if db.query(Task.id).filter(Task.parent_id == sib.id).first():
                from .tree import publish_unblocked_leaves

                publish_unblocked_leaves(db, sib)
            else:
                task_service.transition(db, sib, "published")
    # 全部子任务闭环 → 容器母任务自动结项（TASK-036 / AI-DEC-025 / TASK-007）
    parent = db.get(Task, done.parent_id)
    if parent and parent.status in ("draft", "published") and all(
        s.status == "completed" for s in siblings
    ):
        from app.modules.account.models import utcnow
        from app.modules.notification.service import notify

        parent.completed_at = utcnow()
        task_service.transition(db, parent, "completed")
        notify(db, parent.creator_id, "task", "母任务已全部完成",
               f"《{parent.title}》的全部子任务已闭环，可查看结项报告")


def register_event_handlers() -> None:
    # 只推进 draft 状态的后继、只结项还没结项的母任务，补做时重新读状态即可
    subscribe("task.completed", _on_task_completed, retry=True)
