"""VER 核验单 + ESCA 争议升级阶梯（49 号 spec）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.locks import job_slot
from app.core.errors import conflict, forbidden, not_found
from app.modules.account.models import User, utcnow
from app.modules.wallet import service as wallet

from . import service
from .models import VerificationOrder
from app.core.timefmt import iso

router = APIRouter(tags=["verify"])


class OutcomeIn(BaseModel):
    outcome: str = Field(pattern="^(approved|revised|rejected)$")
    comment: str = Field(default="", max_length=2000)
    revised_output: str = Field(default="", max_length=20000)


def _dump(o: VerificationOrder) -> dict:
    return {
        "id": o.id, "task_id": o.task_id, "status": o.status, "trigger": o.trigger,
        "fee_cents": o.fee_cents, "payer_id": o.payer_id, "verifier_id": o.verifier_id,
        "outcome": o.outcome, "comment": o.comment,
        "revised_output": o.revised_output, "criteria_results": o.criteria_results,
        "deadline": iso(o.deadline),
        "created_at": iso(o.created_at),
    }


def _task(db: Session, task_id: int):
    from app.modules.task.router import _get_task

    return _get_task(db, task_id)


@router.post("/tasks/{task_id}/verification", status_code=201)
def request_verification(task_id: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """下一张核验单。

    VER-002 **谁付费是个有立场的判断**：
    - agent 置信度不足自动升级 → **平台付**。平台自有 agent 没把握是平台的问题，
      让发布方为 AI 的不确定性买单，等于把技术不成熟的成本转嫁给用户。
    - 发布方主动要求核验一个已成功的 run → 发布方付（他额外买的一份确定性）。

    这条有直接的经济后果：置信度阈值调得越松，平台自己掏的核验费越多——
    **这正是它该有的激励**，调松阈值的成本由调的人承担。
    """
    from app.modules.agent import service as agent_service

    task = _task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden("仅发布方可发起核验")
    run = agent_service.latest_run(db, task_id)
    if not run:
        raise conflict("该任务没有 AI 执行记录，无需核验", "no_agent_run")
    if run.status == "running":
        raise conflict("执行中，请稍候", "agent_run_in_progress")

    escalated = run.status == "escalated"
    payer_id = wallet.PLATFORM_USER_ID if escalated else user.id
    order = service.create_order(
        db, task, trigger="escalation" if escalated else "requested",
        agent_run_id=run.id, payer_id=payer_id,
    )
    return _dump(order)


@router.get("/verification-orders")
def open_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """可接的核验单。不能接的**说明理由**——只显示空列表，
    核验人不知道是资格不够还是真没单。"""
    rows = (
        db.query(VerificationOrder)
        .filter(VerificationOrder.status == "open")
        .order_by(VerificationOrder.id.desc())
        .limit(50)
        .all()
    )
    out = []
    for o in rows:
        task = _task(db, o.task_id)
        block = service.verifier_block(db, task, o, user)
        out.append({
            **_dump(o), "category": task.category, "task_title": task.title,
            "claimable": not block, "reason": block,
        })
    return out


@router.post("/verification-orders/{order_id}/claim")
def claim(order_id: int, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    order = db.get(VerificationOrder, order_id)
    if not order:
        raise not_found("核验单不存在")
    if order.status != "open":
        raise conflict("该核验单已被接走或已结束", "not_claimable")
    task = _task(db, order.task_id)
    block = service.verifier_block(db, task, order, user)
    if block:
        raise forbidden(block, "verifier_not_eligible")
    order.verifier_id = user.id
    order.status = "claimed"
    db.add(order)
    return _dump(order)


@router.get("/verification-orders/{order_id}")
def get_order(order_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    order = db.get(VerificationOrder, order_id)
    if not order:
        raise not_found("核验单不存在")
    task = _task(db, order.task_id)
    if user.id not in (task.creator_id, order.verifier_id) and not user.is_admin:
        raise forbidden()
    from app.modules.agent.models import AgentRun

    run = db.get(AgentRun, order.agent_run_id) if order.agent_run_id else None
    return {
        **_dump(order),
        "task_title": task.title, "task_description": task.description,
        "category": task.category,
        "acceptance_criteria": task.acceptance_criteria,
        # 核验人要看的就是这个：AI 产出 + 它自报的置信度 + 平台判据结果
        "agent_output": run.output if run else "",
        "agent_confidence_bps": run.confidence_bps if run else None,
        "agent_criteria_results": run.criteria_results if run else [],
    }


@router.post("/verification-orders/{order_id}/outcome")
def submit(order_id: int, body: OutcomeIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    order = db.get(VerificationOrder, order_id)
    if not order:
        raise not_found("核验单不存在")
    if order.verifier_id != user.id:
        raise forbidden("仅接单的核验人可提交结论")
    task = _task(db, order.task_id)
    return service.submit_outcome(
        db, order, task, outcome=body.outcome, comment=body.comment,
        revised_output=body.revised_output,
    )


@router.post("/verify/jobs/expire-orders")
def expire_orders(db: Session = Depends(get_db), _=Depends(require_job_auth),
                  __=Depends(job_slot("expire_verifications"))):
    """VER-041 超时未接单自动退款。已接单的不自动退——那笔活可能正在做，
    钱退了人还在干是更糟的状态，那种情况走人工。"""
    return service.expire_overdue(db)


# ----------------------------------------------------------------- ESCA 升级阶梯
class EscalateIn(BaseModel):
    task_id: int
    reason: str = Field(min_length=4, max_length=1000)


@router.post("/support/tickets/{ticket_id}/escalate-to-dispute", status_code=201)
def escalate_ticket(ticket_id: int, body: EscalateIn,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ESCA-001 工单转纠纷，**带上下文**。

    不带上下文的话用户要把话重说一遍——而他刚刚已经在工单里说过一次了。
    重说一遍不只是麻烦：**两次陈述不一致会被当成翻供**，在纠纷里对他不利。
    """
    from app.modules.dispute.router import OpenIn, open_dispute
    from app.modules.support.models import Ticket

    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise not_found("工单不存在")
    if ticket.user_id != user.id:
        raise forbidden()
    if ticket.escalated_to_dispute_id:
        raise conflict("该工单已转纠纷", "already_escalated")

    result = open_dispute(body.task_id, OpenIn(reason=body.reason), user, db)

    from app.modules.dispute.models import Dispute

    dispute = db.get(Dispute, result["id"])
    # 上下文进证据链，两边互相能找到
    evidence = dict(dispute.evidence or {})
    evidence["from_ticket"] = {
        "ticket_id": ticket.id, "subject": ticket.subject,
        "body": ticket.body, "support_reply": ticket.reply,
        "created_at": iso(ticket.created_at),
    }
    dispute.evidence = evidence
    ticket.escalated_to_dispute_id = dispute.id
    ticket.status = "escalated"
    db.add_all([dispute, ticket])
    return {"dispute_id": dispute.id, "ticket_id": ticket.id}
