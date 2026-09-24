"""AGT agent 目录、报名与执行（48 号 spec）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User

from . import service
from .models import AgentProfile, AgentRun
from app.core.timefmt import iso

router = APIRouter(tags=["agent"])


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    domains: list[str] = Field(default_factory=list)
    model: str = ""
    system_prompt: str = ""
    cost_per_run_cents: int = Field(default=0, ge=0)
    max_task_budget_cents: int = Field(default=50000, ge=0)
    confidence_threshold_bps: int = Field(default=7000, ge=0, le=10000)


class AgentPatch(BaseModel):
    domains: list[str] | None = None
    model: str | None = None
    system_prompt: str | None = None
    cost_per_run_cents: int | None = Field(default=None, ge=0)
    max_task_budget_cents: int | None = Field(default=None, ge=0)
    confidence_threshold_bps: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


def _public(p: AgentProfile) -> dict:
    """对普通用户可见的字段。**不含 system_prompt 与成本**：
    prompt 泄露等于把判据之外的实现细节交出去，成本是平台的经营数据。"""
    return {
        "user_id": p.user_id, "name": p.name, "domains": p.domains,
        "max_task_budget_cents": p.max_task_budget_cents,
        "runs_total": p.runs_total, "runs_succeeded": p.runs_succeeded,
        "is_active": p.is_active,
    }


def _dump_run(r: AgentRun) -> dict:
    return {
        "id": r.id, "task_id": r.task_id, "status": r.status,
        "confidence_bps": r.confidence_bps, "output": r.output,
        "criteria_results": r.criteria_results, "error": r.error,
        # AGT-051 审核结论对当事人可见；labels 不出（命中的违禁词本身
        # 就是违禁内容，没必要再回显一遍，理由已经在 error 里说清楚了）
        "moderation_status": r.moderation_status,
        "created_at": iso(r.created_at),
        "finished_at": iso(r.finished_at),
    }


# ---------- 平台侧（admin）：agent 是平台自有的，只有平台能注册 ----------
@router.post("/admin/agents", status_code=201)
def create_agent(body: AgentIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    """注册一个平台自有 agent：建 User 行 + profile。

    建 User 行不是为了让它「像个用户」，是为了让托管/纠纷/信用/账本
    **一行都不用改**就对它生效（spec 第 0 节）。
    """
    from app.modules.admin.router import record_audit

    if not body.domains:
        raise bad_request("必须声明至少一个能力领域", "domains_required")
    agent_user = User(
        phone=f"agent:{body.name}",
        nickname=body.name,
        is_agent=True,
        is_verified=True,     # 平台自有，实名由平台承担
        is_adult=True,
        accepting_orders=True,
    )
    db.add(agent_user)
    db.flush()
    profile = AgentProfile(
        user_id=agent_user.id, name=body.name, domains=body.domains,
        model=body.model, system_prompt=body.system_prompt,
        cost_per_run_cents=body.cost_per_run_cents,
        max_task_budget_cents=body.max_task_budget_cents,
        confidence_threshold_bps=body.confidence_threshold_bps,
    )
    db.add(profile)
    record_audit(db, admin.id, "agent_create", "agent", str(agent_user.id), body.name)
    return {"user_id": agent_user.id, "name": profile.name}


@router.get("/admin/agents")
def list_agents_admin(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """带毛利。AGT-016：没有这个数字，「让 agent 接单」是赚是赔谁也说不清。"""
    out = []
    for p in db.query(AgentProfile).all():
        row = _public(p)
        row.update({
            "model": p.model, "cost_per_run_cents": p.cost_per_run_cents,
            "confidence_threshold_bps": p.confidence_threshold_bps,
            "runs_escalated": p.runs_escalated, "runs_failed": p.runs_failed,
            # AGT-052 成本是按配置估算的，不是账单口径——报表上必须这么说
            "margin_is_estimated": True,
            **service.gross_margin_cents(db, p.user_id),
        })
        out.append(row)
    return out


@router.patch("/admin/agents/{agent_user_id}")
def patch_agent(agent_user_id: int, body: AgentPatch, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    from app.modules.admin.router import record_audit

    p = db.get(AgentProfile, agent_user_id)
    if not p:
        raise not_found("助理不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    db.add(p)
    record_audit(db, admin.id, "agent_update", "agent", str(agent_user_id), "")
    return _public(p)


# ---------- 用户侧 ----------
@router.get("/agents")
def list_agents(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_public(p) for p in
            db.query(AgentProfile).filter(AgentProfile.is_active.is_(True)).all()]


@router.get("/tasks/{task_id}/eligible-agents")
def eligible_agents(task_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """这个任务哪些 agent 能接，以及不能接的**说明理由**。

    只说「没有可用助理」没有意义——发布方不知道是因为要到场、
    还是因为金额超限，也就不知道改什么。
    """
    from app.modules.task.router import _get_task

    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    out = []
    for p in db.query(AgentProfile).filter(AgentProfile.is_active.is_(True)).all():
        block = service.eligibility_block(db, p, task)
        out.append({**_public(p), "eligible": not block, "reason": block})
    return out


@router.post("/tasks/{task_id}/agent-apply", status_code=201)
def agent_apply(task_id: int, agent_user_id: int,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """让指定 agent 报名。**由发布方主动触发，不自动派单**——
    让 AI 接自己的活是一个需要知情的选择，静默派单等于替用户做主。

    走既有 `Application`，不给 agent 开后门（AGT-020）。
    """
    from app.modules.task.models import Application
    from app.modules.task.router import _get_task

    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden("仅发布方可邀请 AI 助理")
    if task.status != "published":
        raise conflict("任务不在招募中", "not_recruiting")
    profile = service.get_profile(db, agent_user_id)
    if not profile:
        raise not_found("助理不存在")
    service.assert_eligible(db, profile, task)
    dup = (
        db.query(Application)
        .filter(Application.task_id == task_id, Application.applicant_id == agent_user_id,
                Application.status != "withdrawn")
        .first()
    )
    if dup:
        raise conflict("该助理已报名", "already_applied")
    row = Application(task_id=task_id, applicant_id=agent_user_id,
                      bid_cents=task.budget_cents,
                      message=f"由平台 AI 助理「{profile.name}」承接")
    db.add(row)
    db.flush()
    return {"id": row.id, "status": row.status, "agent_user_id": agent_user_id}


@router.post("/tasks/{task_id}/agent-run", status_code=201)
def trigger_run(task_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    from app.modules.contract.models import Contract
    from app.modules.task.router import _get_task

    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden("仅发布方可触发执行")
    if not task.executor_id:
        raise conflict("任务尚未成交", "no_executor")
    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    run = service.run_agent(db, task, contract.id if contract else None)
    # AGT-060 执行成功即由平台代为提交交付。少了这一步，任务在生产里
    # 永远停在 in_progress——agent 没有登录态，没人能替它按「提交交付」。
    delivered = service.submit_agent_delivery(db, task)
    return {**_dump_run(run), "delivered": delivered, "task_status": task.status}


@router.get("/tasks/{task_id}/agent-runs")
def list_runs(task_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    from app.modules.task.router import _get_task

    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id) and not user.is_admin:
        raise forbidden()
    rows = db.query(AgentRun).filter(AgentRun.task_id == task_id).order_by(AgentRun.id).all()
    return {
        "runs": [_dump_run(r) for r in rows],
        # 客户端的「提交交付」按钮读这个，与服务端 deliver 端点同一判断（单一来源）
        "delivery_block": service.delivery_block(db, task),
    }
