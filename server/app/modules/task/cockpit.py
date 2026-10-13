"""SPACE-024 / AI-DEC-021 合作驾驶舱（120 号 spec）：一棵树、一条关键路径、一本预算账、一张预警单。

母任务拆成十几步、分给几个人之后，发布方要回答四个问题：
**现在做到哪了？卡在谁那里？钱花了多少？哪里要我出手？**
原来的 `/tasks/{id}/tree` 只回答第一个（按预算加权的进度），而且只看一层。

取数一律按层批量查（与节点数无关的几条查询，115 号闸门同一条要求），节点数有上限。
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.modules.account.models import User, utcnow
from app.modules.task.models import Application, Task

MAX_DEPTH = 6
MAX_NODES = 300
STALE_RECRUIT_DAYS = 3       # 招募超过 3 天没人报名：该改价、改说明或主动邀约了
DONE = ("completed",)
OPEN_DISPUTE = ("open", "appealed")
STATUS_NAMES = {"draft": "未开始", "published": "招募中", "matched": "已成交", "in_progress": "进行中",
                "pending_acceptance": "待验收", "completed": "已完成", "cancelled": "已取消", "disputed": "纠纷中"}


def _descendants(db: Session, root: Task) -> list[Task]:
    out, frontier, depth = [], [root.id], 0
    while frontier and depth < MAX_DEPTH and len(out) < MAX_NODES:
        rows = db.query(Task).filter(Task.parent_id.in_(frontier)).order_by(Task.id).all()
        out.extend(rows)
        frontier = [r.id for r in rows]
        depth += 1
    return out[:MAX_NODES]


def critical_path(nodes: list[Task]) -> list[int]:
    """剩余步骤最多的那条依赖链（只在同一层兄弟之间有依赖）。

    没有工期估计，就不假装算「最长工期」：按**还没完成的步骤数**取最长链——
    这条链上任何一步拖一天，整件事就晚一天。已完成的步骤不计入长度。
    """
    by_id = {n.id: n for n in nodes}
    memo: dict[int, tuple[int, list[int]]] = {}

    def longest(nid: int, seen: frozenset) -> tuple[int, list[int]]:
        if nid in memo:
            return memo[nid]
        n = by_id[nid]
        best = (0, [])
        for dep in (n.depends_on or []):
            if dep in by_id and dep not in seen:
                cand = longest(dep, seen | {nid})
                if cand[0] > best[0]:
                    best = cand
        own = 0 if n.status in DONE or n.status == "cancelled" else 1
        memo[nid] = (best[0] + own, best[1] + [nid])
        return memo[nid]

    best: tuple[int, list[int]] = (0, [])
    for n in nodes:
        if n.status == "cancelled":
            continue
        cand = longest(n.id, frozenset())
        if cand[0] > best[0]:
            best = cand
    return [i for i in best[1] if by_id[i].status not in DONE] if best[0] else []


def cockpit(db: Session, parent: Task) -> dict:
    from app.core.timefmt import iso
    from app.modules.contract.models import Contract
    from app.modules.dispute.models import Dispute

    now = utcnow()
    nodes = _descendants(db, parent)
    ids = [n.id for n in nodes]
    has_children = {n.parent_id for n in nodes}
    leaves = [n for n in nodes if n.id not in has_children]
    contracts = {c.task_id: c for c in db.query(Contract).filter(Contract.task_id.in_(ids or [-1]))}
    disputes = {d.task_id for d in db.query(Dispute.task_id).filter(
        Dispute.task_id.in_(ids or [-1]), Dispute.status.in_(OPEN_DISPUTE))}
    applicants = dict(db.query(Application.task_id, Application.id).filter(Application.task_id.in_(ids or [-1])))
    people = {u.id: u.nickname for u in db.query(User).filter(
        User.id.in_({n.executor_id for n in nodes if n.executor_id} or {-1}))}
    status_of = {n.id: n.status for n in nodes}

    # ---- 预算账：只算叶子（容器步骤自己不托管，算进去会重复）
    planned = parent.budget_cents
    allocated = committed = paid = 0
    for n in leaves:
        if n.status == "cancelled":
            continue
        allocated += n.budget_cents
        c = contracts.get(n.id)
        if c is None or c.status in ("cancelled", "refunded", "pending_signatures"):
            continue
        if c.status == "released":
            paid += c.amount_cents
        else:
            committed += c.amount_cents - (c.released_cents or 0)
            paid += c.released_cents or 0

    # ---- 预警
    alerts = []
    for n in leaves:
        if n.id in disputes:
            alerts.append({"task_id": n.id, "kind": "dispute", "text": f"「{n.title}」在纠纷中，相关款项已冻结"})
        elif n.deadline and n.deadline < now and n.status not in DONE + ("cancelled",):
            alerts.append({"task_id": n.id, "kind": "overdue",
                           "text": f"「{n.title}」已过截止时间（{STATUS_NAMES.get(n.status, n.status)}）：催办、改期或发起纠纷"})
        elif n.status == "published" and n.id not in applicants and n.created_at < now - timedelta(days=STALE_RECRUIT_DAYS):
            alerts.append({"task_id": n.id, "kind": "no_applicants",
                           "text": f"「{n.title}」招募超过 {STALE_RECRUIT_DAYS} 天还没人报名：改价、改说明或主动邀约"})
        elif n.status == "pending_acceptance":
            alerts.append({"task_id": n.id, "kind": "to_accept", "text": f"「{n.title}」已交付，等你验收"})
    if planned and allocated > planned:
        alerts.append({"task_id": parent.id, "kind": "over_budget",
                       "text": f"各步骤预算合计 ¥{allocated / 100:.2f}，超出母任务预算 ¥{planned / 100:.2f}"})

    path = critical_path([n for n in leaves])
    done_budget = sum(n.budget_cents for n in leaves if n.status in DONE)
    live = [n for n in leaves if n.status != "cancelled"]
    return {
        "task_id": parent.id, "title": parent.title, "status": parent.status,
        "progress_pct": round(done_budget * 100 / (sum(n.budget_cents for n in live) or 1), 1) if live else 0,
        "steps_total": len(live), "steps_done": sum(1 for n in live if n.status in DONE),
        "budget": {"planned_cents": planned, "allocated_cents": allocated, "committed_cents": committed,
                   "paid_cents": paid, "remaining_cents": max(planned - committed - paid, 0)},
        "critical_path": path,
        "alerts": alerts,
        "nodes": [{
            "id": n.id, "parent_id": n.parent_id, "title": n.title, "status": n.status,
            "status_name": STATUS_NAMES.get(n.status, n.status), "budget_cents": n.budget_cents,
            "is_container": n.id in has_children, "depends_on": list(n.depends_on or []),
            "blocked_by": [d for d in (n.depends_on or []) if status_of.get(d) not in DONE and d in status_of],
            "executor_id": n.executor_id, "executor_nickname": people.get(n.executor_id) if n.executor_id else None,
            "deadline": iso(n.deadline),
            "overdue": bool(n.deadline and n.deadline < now and n.status not in DONE + ("cancelled",)),
            "on_critical_path": n.id in path,
            "in_dispute": n.id in disputes,
        } for n in nodes],
    }
