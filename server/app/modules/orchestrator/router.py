"""ORC 编排 API：创建目标 → 逐轮 tick 推进 → 查看步骤与完成度。

一次 tick 就是 agent 的一步：规划/分发（发任务给人）/观测（验收结果）/评估/迭代。
所有资金动作仍走既有托管合约链路，护栏见 service。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.locks import job_slot
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import conflict, forbidden, not_found
from app.modules.account.models import User

from . import service
from .models import Mission, MissionEvent, MissionStep, StepReview
from app.core.timefmt import iso

router = APIRouter(tags=["orchestrator"])


class MissionIn(BaseModel):
    goal: str = Field(min_length=2, max_length=200)
    detail: str = Field(default="", max_length=2000)
    category: str = Field(default="跑腿", max_length=50)
    budget_cap_cents: int = Field(gt=0)
    max_iterations: int = Field(default=5, ge=1, le=20)
    acceptance_criteria: list[str] = Field(default_factory=list)
    # ORC-061 默认关：发起人授权了「自动花钱」，不等于授权「活由 AI 做」。
    allow_agents: bool = False
    # AGT-084 默认关：允许分发时用平台经验工具生成草稿（只出草稿，等你确认）
    allow_tools: bool = False


class ToolsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_tools: bool


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
        "model_calls": m.model_calls, "allow_agents": m.allow_agents, "allow_tools": m.allow_tools,
        "acceptance_criteria": m.acceptance_criteria,
        "last_error": m.last_error, "created_at": iso(m.created_at),
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
    body: MissionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    """ORC-001 创建编排目标（尚未分发，需 tick 推进）。"""
    m = Mission(
        owner_id=user.id, goal=body.goal, detail=body.detail, category=body.category,
        budget_cap_cents=body.budget_cap_cents, max_iterations=body.max_iterations,
        acceptance_criteria=body.acceptance_criteria, allow_agents=body.allow_agents,
        allow_tools=body.allow_tools,
    )
    db.add(m)
    db.flush()
    return _dump(m)


@router.get("/missions")
def my_missions(
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
):
    q = db.query(Mission).filter(Mission.owner_id == user.id)
    if status:
        q = q.filter(Mission.status == status)
    return [_dump(m) for m in q.order_by(Mission.id.desc()).offset(offset).limit(limit)]


@router.get("/missions/{mission_id}")
def get_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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
             # ORC-060 这一步是不是给了 AI 助理——发起人有权看见这件事
             "agent_user_id": s.agent_user_id,
             "acceptance": s.acceptance or [],
             "review_verdict": s.review_verdict, "review_score": s.review_score,
             "review_missing": s.review_missing or [],
             "tool_drafts": s.tool_drafts or []}
            for s in steps
        ],
        # AIO-023 时间线：人类可读的「做了什么 / 卡在哪 / 下一步」
        "timeline": [
            {"iteration": e.iteration, "action": e.action, "summary": e.summary,
             "at": iso(e.created_at)}
            for e in db.query(MissionEvent)
            .filter(MissionEvent.mission_id == mission_id)
            .order_by(MissionEvent.id).all()
        ],
    }


@router.get("/missions/{mission_id}/steps/{step_id}/reviews")
def step_reviews(
    mission_id: int, step_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
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
         "duration_ms": r.duration_ms, "at": iso(r.created_at)}
        for r in rows
    ]}


@router.post("/missions/{mission_id}/tick")
def tick_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    """ORC-002 推进一轮：规划 → 观测 → 评估 → 分发/迭代 → 停机判定。"""
    m = _get_mission(db, mission_id, user)
    return service.tick(db, m)


@router.post("/missions/{mission_id}/cancel")
def cancel_mission(
    mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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


@router.get("/missions/{mission_id}/summary")
def mission_summary(mission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AGT-091 编排复盘（133 号 spec）：花了多少、几轮、哪些步骤整改过、评审多少分、经验工具草稿用了几份、下一步建议。"""
    m = _get_mission(db, mission_id, user)
    steps = db.query(MissionStep).filter(MissionStep.mission_id == m.id).order_by(MissionStep.id).all()
    live = [s for s in steps if s.status != "superseded"]
    done = [s for s in live if s.status == "done"]
    failed = [s for s in live if s.status == "failed"]
    remedies = [s for s in steps if s.is_remedy]
    scored = [s.review_score for s in done if s.review_verdict]
    drafts = [d for s in steps for d in (s.tool_drafts or [])]
    reworked = sorted({s.title for s in remedies})
    end = m.updated_at if m.status in ("succeeded", "failed", "cancelled") else None
    days = max((end - m.created_at).days, 0) if end and m.created_at else None
    highlights = []
    if m.status == "succeeded":
        highlights.append(f"达标：{len(done)} 步全部验收，平均评审 {m.quality_pct} 分")
    if reworked:
        highlights.append(f"整改过 {len(reworked)} 步：{'、'.join(reworked[:5])}")
    if m.spent_cents > m.budget_cap_cents * 0.9:
        highlights.append("花费接近预算上限：下次同类目标可以把上限放宽一些，或者拆得更细")
    if drafts:
        adopted = sum(1 for d in drafts if d.get("status") == "adopted")
        highlights.append(f"经验工具生成 {len(drafts)} 份草稿，你采用了 {adopted} 份")
    nxt = {
        "succeeded": "可以把这次的做法存进个人知识库，下次同类目标直接套用",
        "failed": "看看没通过的步骤卡在哪：改验收要点或预算后再建一个编排",
        "cancelled": "已取消：还在做的任务照常结算",
        "blocked": "卡住了：看时间线里最后一条，补预算或改目标后再推进",
    }.get(m.status, "还在进行：推进下一轮，或等已发布的任务有人接")
    return {
        "mission_id": m.id, "goal": m.goal, "status": m.status, "rounds": m.iteration, "max_rounds": m.max_iterations,
        "spent_cents": m.spent_cents, "committed_cents": m.committed_cents, "cap_cents": m.budget_cap_cents,
        "steps_total": len(live), "steps_done": len(done), "steps_failed": len(failed), "remedies": len(remedies),
        "avg_review_score": round(sum(scored) / len(scored)) if scored else None,
        "drafts_total": len(drafts), "drafts_adopted": sum(1 for d in drafts if d.get("status") == "adopted"),
        "duration_days": days, "highlights": highlights, "next": nxt,
    }


@router.put("/missions/{mission_id}/tools")
def set_tools(mission_id: int, body: ToolsIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")):
    """AGT-084 开关：之后分发的步骤才会用经验工具；已经生成的草稿不受影响。只有发起人能改。"""
    m = _get_mission(db, mission_id, user)
    if m.owner_id != user.id:
        raise forbidden("只有发起人能授权编排使用经验工具")
    m.allow_tools = body.allow_tools
    db.add(m)
    db.flush()
    return _dump(m)


def _draft(db: Session, mission_id: int, step_id: int, invocation_id: int, user: User):
    m = _get_mission(db, mission_id, user)
    if m.owner_id != user.id:
        raise forbidden("只有发起人能确认编排生成的草稿")
    s = db.get(MissionStep, step_id)
    if s is None or s.mission_id != m.id:
        raise not_found("这一步不存在")
    drafts = [dict(d) for d in (s.tool_drafts or [])]
    d = next((x for x in drafts if x["invocation_id"] == invocation_id), None)
    if d is None:
        raise not_found("这一步没有这份草稿")
    if d["status"] != "pending":
        raise conflict("这份草稿已经处理过了", "draft_already_decided")
    return s, drafts, d


@router.post("/missions/{mission_id}/steps/{step_id}/drafts/{invocation_id}/adopt")
def adopt_draft(mission_id: int, step_id: int, invocation_id: int,
                user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AGT-084 采用编排生成的草稿。采用只是标记，不会替你发给任何人。"""
    return _decide(db, mission_id, step_id, invocation_id, user, "adopt")


@router.post("/missions/{mission_id}/steps/{step_id}/drafts/{invocation_id}/discard")
def discard_draft(mission_id: int, step_id: int, invocation_id: int,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """AGT-084 丢弃编排生成的草稿（留着记录，标为已丢弃）。"""
    return _decide(db, mission_id, step_id, invocation_id, user, "discard")


def _decide(db: Session, mission_id: int, step_id: int, invocation_id: int, user: User, decision: str) -> dict:
    from app.modules.knowledge.models import UnitInvocation

    s, drafts, d = _draft(db, mission_id, step_id, invocation_id, user)
    d["status"] = "adopted" if decision == "adopt" else "discarded"
    s.tool_drafts = drafts
    inv = db.get(UnitInvocation, invocation_id)
    if inv is not None:
        inv.adopted, inv.discarded = decision == "adopt", decision == "discard"
        db.add(inv)
    db.add(s)
    db.flush()
    return {"step_id": s.id, "invocation_id": invocation_id, "status": d["status"]}


@router.post("/missions/jobs/tick-all")
def tick_all(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
        __=Depends(job_slot("mission_tick_all"), scope="function")):
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
