"""ORC 编排 API：创建目标 → 逐轮 tick 推进 → 查看步骤与完成度。

一次 tick 就是 agent 的一步：规划/分发（发任务给人）/观测（验收结果）/评估/迭代。
所有资金动作仍走既有托管合约链路，护栏见 service。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.locks import job_slot
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import forbidden, not_found
from app.modules.account.models import User

from . import service
from .models import Mission, MissionEvent, MissionStep, StepReview

router = APIRouter(tags=["orchestrator"])


class MissionIn(BaseModel):
    goal: str = Field(min_length=2, max_length=200)
    detail: str = Field(default="", max_length=2000)
    category: str = Field(default="跑腿", max_length=50)
    budget_cap_cents: int = Field(gt=0)
    max_iterations: int = Field(default=5, ge=1, le=20)
    acceptance_criteria: list[str] = Field(default_factory=list)


def _dump(m: Mission) -> dict:
    return {
        "id": m.id, "owner_id": m.owner_id, "goal": m.goal, "detail": m.detail,
        "category": m.category, "status": m.status,
        "budget_cap_cents": m.budget_cap_cents,
        # AIO-024 两个量语义不同：committed 是当前占用（取消会释放），
        # spent 是任务完成放款后的真实花费
        "committed_cents": m.committed_cents, "spent_cents": m.spent_cents,
        "iteration": m.iteration, "max_iterations": m.max_iterations,
        "completion_pct": m.completion_pct, "quality_pct": m.quality_pct,
        "model_calls": m.model_calls,
        "acceptance_criteria": m.acceptance_criteria,
        "last_error": m.last_error, "created_at": m.created_at.isoformat(),
    }


def _get_mission(db: Session, mission_id: int, user: User) -> Mission:
    m = db.get(Mission, mission_id)
    if not m:
        raise not_found("编排目标不存在")
    if m.owner_id != user.id and not user.is_admin:
        raise forbidden()
    return m


@router.post("/missions", status_code=201)
def create_mission(
    body: MissionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """ORC-001 创建编排目标（尚未分发，需 tick 推进）。"""
    m = Mission(
        owner_id=user.id, goal=body.goal, detail=body.detail, category=body.category,
        budget_cap_cents=body.budget_cap_cents, max_iterations=body.max_iterations,
        acceptance_criteria=body.acceptance_criteria,
    )
    db.add(m)
    db.flush()
    return _dump(m)


@router.get("/missions")
def my_missions(
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    q = db.query(Mission).filter(Mission.owner_id == user.id)
    if status:
        q = q.filter(Mission.status == status)
    return [_dump(m) for m in q.order_by(Mission.id.desc()).offset(offset).limit(limit)]


@router.get("/missions/{mission_id}")
def get_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    m = _get_mission(db, mission_id, user)
    steps = (
        db.query(MissionStep).filter(MissionStep.mission_id == mission_id)
        .order_by(MissionStep.id).all()
    )
    return {
        **_dump(m),
        "steps": [
            {"id": s.id, "iteration": s.iteration, "tool": s.tool, "title": s.title,
             "task_id": s.task_id, "status": s.status, "observation": s.observation,
             "is_remedy": bool(s.is_remedy), "budget_cents": s.args.get("budget_cents"),
             "parent_step_id": s.parent_step_id, "attempt": s.attempt,
             "acceptance": s.acceptance or [],
             "review_verdict": s.review_verdict, "review_score": s.review_score,
             "review_missing": s.review_missing or []}
            for s in steps
        ],
        # AIO-023 时间线：人类可读的「做了什么 / 卡在哪 / 下一步」
        "timeline": [
            {"iteration": e.iteration, "action": e.action, "summary": e.summary,
             "at": e.created_at.isoformat()}
            for e in db.query(MissionEvent)
            .filter(MissionEvent.mission_id == mission_id)
            .order_by(MissionEvent.id).all()
        ],
    }


@router.get("/missions/{mission_id}/steps/{step_id}/reviews")
def step_reviews(
    mission_id: int, step_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """AIO-013 评审留痕：谁判的、用哪版提示词、依据什么、多久。

    没有留痕的自动判定在纠纷里毫无价值——这是它能被拿出来说事的前提。
    """
    _get_mission(db, mission_id, user)
    step = db.get(MissionStep, step_id)
    if not step or step.mission_id != mission_id:
        raise not_found("步骤不存在")
    rows = db.query(StepReview).filter(StepReview.step_id == step_id) \
             .order_by(StepReview.id).all()
    return {"reviews": [
        {"id": r.id, "reviewer": r.reviewer, "prompt_version": r.prompt_version,
         "verdict": r.verdict, "score": r.score, "reasons": r.reasons,
         "missing": r.missing, "input_digest": r.input_digest,
         "duration_ms": r.duration_ms, "at": r.created_at.isoformat()}
        for r in rows
    ]}


@router.post("/missions/{mission_id}/tick")
def tick_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """ORC-002 推进一轮：规划 → 观测 → 评估 → 分发/迭代 → 停机判定。"""
    m = _get_mission(db, mission_id, user)
    return service.tick(db, m)


@router.post("/missions/{mission_id}/cancel")
def cancel_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """ORC-004 人工停机：随时可中止 agent（未成交的挂单一并下架）。"""
    from app.modules.task.models import Task
    from app.modules.task.service import transition as task_transition

    m = _get_mission(db, mission_id, user)
    service.transition(db, m, "cancelled")
    closed = 0
    steps = db.query(MissionStep).filter(
        MissionStep.mission_id == mission_id, MissionStep.status == "dispatched"
    ).all()
    for s in steps:
        task = db.get(Task, s.task_id) if s.task_id else None
        if task and task.status in ("draft", "published"):
            task_transition(db, task, "cancelled", {"cancelled_by": "mission_cancelled"})
            s.status = "failed"
            s.observation = "编排已中止，挂单下架"
            # AIO-024 下架 = 钱没花出去，释放占用额度
            m.committed_cents = max(0, m.committed_cents - int(s.args.get("budget_cents", 0)))
            db.add_all([s, m])
            closed += 1
    return {**_dump(m), "closed_open_tasks": closed}


@router.post("/missions/jobs/tick-all")
def tick_all(db: Session = Depends(get_db), _=Depends(require_job_auth),
        __=Depends(job_slot("mission_tick_all"))):
    """ORC-006 自动驱动：定时器批量推进运行中的编排（agent loop 的心跳）。"""
    rows = db.query(Mission).filter(Mission.status.in_(("running", "planning"))).all()
    ticked = 0
    for m in rows:
        try:
            service.tick(db, m)
            ticked += 1
        except Exception:  # 单个编排出错不影响其它（护栏/状态冲突等）
            continue
    return {"ticked": ticked}
