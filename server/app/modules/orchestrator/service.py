"""ORC 编排引擎：plan → dispatch → observe → evaluate 的一次 tick。

与 agent harness 的对应关系：
- tool 调用 = 发布任务给平台上的其他人（真实合约托管 + 验收 + 纠纷兜底）；
- observation = 任务验收结果（completed 成果 / cancelled 失败 / 驳回问题）；
- 迭代 = 观测到问题后自动生成「修复步」再次分发，直到达标或触及护栏。

护栏（ORC-004）是本模块的第一性要求：agent 会自动花钱，必须有预算上限、
迭代上限与显式停机条件，且所有资金动作仍复用既有托管/守恒/审计链路。
"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.modules.account.models import utcnow

from .models import Mission, MISSION_TRANSITIONS, MissionStep


def transition(db: Session, mission: Mission, new_status: str) -> Mission:
    """ORC-003 编排状态机：白名单流转，非法流转 409（与任务状态机同治理）。"""
    allowed = MISSION_TRANSITIONS.get(mission.status, set())
    if new_status not in allowed:
        raise conflict(
            f"编排状态不允许从 {mission.status} 变更为 {new_status}", "invalid_mission_transition"
        )
    mission.status = new_status
    mission.updated_at = utcnow()
    db.add(mission)
    return mission


def plan(db: Session, mission: Mission) -> list[MissionStep]:
    """规划：复用 AI 分解网关把目标拆成可分发的工具调用（无 Key 时走模板引擎）。"""
    from app.modules.decompose.llm import get_gateway

    existing = db.query(MissionStep).filter(MissionStep.mission_id == mission.id).count()
    if existing:
        return []
    from app.core.config import settings

    # ORC-004 规划只用上限的一部分，其余留作重试预留金
    plan_budget = mission.budget_cap_cents * (10000 - settings.ORC_PLAN_RESERVE_BPS) // 10000
    items = get_gateway().decompose(
        db, mission.goal, mission.detail, mission.category, plan_budget
    )
    steps = []
    for item in items:
        step = MissionStep(
            mission_id=mission.id, iteration=0, tool="publish_task",
            title=item["title"],
            args={
                "title": item["title"][:120],
                "description": item.get("description", ""),
                "category": mission.category,
                "budget_cents": item["budget_cents"],
                "required_skills": item.get("required_skills", []),
            },
        )
        db.add(step)
        steps.append(step)
    db.flush()
    return steps


def _dispatch_step(db: Session, mission: Mission, step: MissionStep) -> None:
    """分发一步 = 调用「发布任务」这个工具（真实建单并进广场招募）。"""
    from app.modules.task.models import Task
    from app.modules.task.service import transition as task_transition, validate_publishable

    budget = int(step.args.get("budget_cents", 0))
    if budget <= 0:
        step.status = "failed"
        step.observation = "预算为 0，无法分发"
        db.add(step)
        return
    # ORC-004 预算护栏：累计已承诺预算不得超过上限
    if mission.spent_cents + budget > mission.budget_cap_cents:
        raise bad_request(
            f"超出编排预算上限（{mission.budget_cap_cents} 分），本步需 {budget} 分",
            "budget_cap_exceeded",
        )
    task = Task(
        creator_id=mission.owner_id,
        title=step.args["title"],
        description=step.args.get("description", ""),
        category=step.args.get("category", mission.category),
        required_skills=step.args.get("required_skills", []),
        budget_cents=budget,
        is_remote=True,
    )
    db.add(task)
    db.flush()
    validate_publishable(task, db)
    task_transition(db, task, "published")
    step.task_id = task.id
    step.status = "dispatched"
    mission.spent_cents += budget
    db.add_all([step, mission])


def observe(db: Session, mission: Mission) -> list[dict]:
    """观测：读取已分发步骤对应任务的真实状态，转成 observation。"""
    from app.modules.task.models import Task

    out = []
    steps = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "dispatched")
        .all()
    )
    for step in steps:
        task = db.get(Task, step.task_id) if step.task_id else None
        if not task:
            continue
        if task.status == "completed":
            step.status = "done"
            step.observation = f"任务 #{task.id} 已验收通过（驳回 {task.reject_count} 次）"
        elif task.status == "cancelled":
            step.status = "failed"
            step.observation = f"任务 #{task.id} 已取消/流单，需要修复步重试"
        elif task.status == "disputed":
            step.observation = f"任务 #{task.id} 进入纠纷仲裁，暂停推进"
        else:
            step.observation = f"任务 #{task.id} 进行中（{task.status}）"
        db.add(step)
        out.append({"step_id": step.id, "task_id": task.id,
                    "task_status": task.status, "observation": step.observation})
    return out


def evaluate(db: Session, mission: Mission) -> dict:
    """评估：完成度 = 已验收步数 / 总步数；并汇总待修复问题。"""
    rows = db.query(MissionStep).filter(MissionStep.mission_id == mission.id).all()
    # superseded：已被修复步取代的旧步，不再计入分母，否则任何一次失败都会
    # 让编排永远无法达到 100%（修复成功也没用）——这是循环能收敛的关键
    steps = [s for s in rows if s.status != "superseded"]
    total = len(steps)
    done = sum(1 for s in steps if s.status == "done")
    failed = [s for s in steps if s.status == "failed"]
    mission.completion_pct = int(done * 100 / total) if total else 0
    db.add(mission)
    return {"total_steps": total, "done": done, "failed": len(failed),
            "superseded": sum(1 for s in rows if s.status == "superseded"),
            "completion_pct": mission.completion_pct,
            "issues": [{"step_id": s.id, "title": s.title, "observation": s.observation}
                       for s in failed]}


def _make_remedy_steps(db: Session, mission: Mission) -> list[MissionStep]:
    """迭代：为失败步生成修复步（同规格重发），受迭代与预算护栏约束。"""
    db.flush()  # 会话 autoflush=False：先落盘 observe 的状态改动，否则 SQL 过滤读到旧值
    failed = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "failed")
        .all()
    )
    remedies = []
    for s in failed:
        # 已经为该步生成过修复步则不重复（幂等）
        dup = (
            db.query(MissionStep)
            .filter(MissionStep.mission_id == mission.id,
                    MissionStep.title == f"[修复] {s.title}")
            .first()
        )
        if dup:
            continue
        r = MissionStep(
            mission_id=mission.id, iteration=mission.iteration + 1, tool="publish_task",
            title=f"[修复] {s.title}", args=dict(s.args), is_remedy=1,
        )
        db.add(r)
        s.status = "superseded"  # 原步交由修复步接续，不再算作未决失败
        s.observation = f"{s.observation}（已生成修复步接续）"
        db.add(s)
        remedies.append(r)
    db.flush()
    return remedies


def tick(db: Session, mission: Mission) -> dict:
    """推进一轮循环：规划（首轮）→ 观测 → 评估 → 分发/迭代 → 停机判定。"""
    if mission.status in ("succeeded", "failed", "cancelled"):
        raise conflict("编排已结束，不可继续推进", "mission_closed")

    planned = plan(db, mission) if mission.status == "planning" else []
    if mission.status == "planning":
        transition(db, mission, "running")

    observations = observe(db, mission)
    report = evaluate(db, mission)

    # 达标：全部步骤验收通过 → 成功停机
    if report["total_steps"] and report["done"] == report["total_steps"]:
        transition(db, mission, "succeeded")
        return {"action": "completed", "planned": len(planned),
                "observations": observations, **report, "status": mission.status}

    # 有失败步 → 生成修复步（快速迭代），受迭代上限约束
    remedies = []
    if report["failed"]:
        if mission.iteration >= mission.max_iterations:
            mission.last_error = "达到迭代上限仍有未完成步骤"
            transition(db, mission, "failed")
            db.add(mission)
            return {"action": "give_up", "observations": observations, **report,
                    "status": mission.status}
        remedies = _make_remedy_steps(db, mission)
        mission.iteration += 1
        db.add(mission)

    # 分发所有待分发步（含本轮新生成的修复步），预算不足则挂起等待人工决策
    db.flush()
    pending = (
        db.query(MissionStep)
        .filter(MissionStep.mission_id == mission.id, MissionStep.status == "pending")
        .order_by(MissionStep.id).all()
    )
    dispatched = 0
    for step in pending:
        try:
            _dispatch_step(db, mission, step)
            dispatched += 1 if step.status == "dispatched" else 0
        except Exception as exc:  # 预算护栏等 → 挂起而非失败，保留人工介入余地
            detail = getattr(exc, "detail", None)
            mission.last_error = (detail or {}).get("message", str(exc))[:300] \
                if isinstance(detail, dict) else str(exc)[:300]
            transition(db, mission, "blocked")
            db.add(mission)
            return {"action": "blocked", "dispatched": dispatched,
                    "observations": observations, **report,
                    "status": mission.status, "error": mission.last_error}

    if mission.status == "blocked" and dispatched:
        transition(db, mission, "running")
    report = evaluate(db, mission)
    return {"action": "dispatched" if dispatched else "waiting",
            "planned": len(planned), "dispatched": dispatched,
            "remedies": len(remedies), "observations": observations,
            **report, "status": mission.status}
