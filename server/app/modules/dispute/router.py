from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_job_auth
from app.core.errors import conflict, forbidden, not_found
from app.core.events import publish
from app.modules.account import service as credit
from app.modules.account.models import User, utcnow
from app.modules.contract import service as contract_service
from app.modules.contract.models import Contract
from app.modules.im.models import Conversation, Message
from app.modules.task.models import ProgressLog, Task
from app.modules.task.service import transition

from .models import Dispute

router = APIRouter(tags=["dispute"])


class OpenIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


class ShareIn(BaseModel):
    executor_share_bps: int = Field(ge=0, le=10000)
    reason: str = ""


def _dump(d: Dispute) -> dict:
    return {
        "id": d.id, "task_id": d.task_id, "contract_id": d.contract_id,
        "opened_by": d.opened_by, "reason": d.reason, "status": d.status,
        "evidence": d.evidence, "settlement_proposal": d.settlement_proposal,
        "verdict_executor_share_bps": d.verdict_executor_share_bps,
        "verdict_reason": d.verdict_reason,
        "split_base_cents": d.split_base_cents,  # DSP-008 裁决/复核分账基数
        "escalated": d.escalated,  # DSP-009 SLA 超期升级标记
    }


@router.post("/tasks/{task_id}/disputes", status_code=201)
def open_dispute(
    task_id: int, body: OpenIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """DSP-001/002/003：发起 → 冻结资金 → 自动归集证据链。"""
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden("仅任务当事人可发起纠纷")
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract or contract.status != "funded":
        raise conflict("仅托管中的任务可发起纠纷", "not_disputable")
    if db.query(Dispute).filter(Dispute.task_id == task_id, Dispute.status == "open").first():
        raise conflict("已存在进行中的纠纷", "dispute_exists")

    contract_service.freeze(db, contract)  # SC-008
    transition(db, task, "disputed")

    # DSP-003 证据链自动归集：合约条款 + 沟通记录 + 履约留痕
    conv = db.query(Conversation).filter(Conversation.task_id == task_id).first()
    msg_count = (
        db.query(Message).filter(Message.conversation_id == conv.id).count() if conv else 0
    )
    logs = db.query(ProgressLog).filter(ProgressLog.task_id == task_id).all()
    evidence = {
        "contract_terms": contract.terms,
        "conversation_id": conv.id if conv else None,
        "message_count": msg_count,
        "progress_logs": [
            {"kind": log.kind, "content": log.content, "at": log.created_at.isoformat()}
            for log in logs
        ],
        "reject_count": task.reject_count,
    }
    dispute = Dispute(
        task_id=task_id, contract_id=contract.id, opened_by=user.id,
        reason=body.reason, evidence=evidence,
    )
    db.add(dispute)
    db.flush()
    publish(db, "dispute.opened", {
        "dispute_id": dispute.id, "task_id": task_id,
        "parties": [task.creator_id, task.executor_id],
    })
    return _dump(dispute)


def _get_dispute(db: Session, dispute_id: int) -> tuple[Dispute, Task, Contract]:
    dispute = db.get(Dispute, dispute_id)
    if not dispute:
        raise not_found("纠纷不存在")
    return dispute, db.get(Task, dispute.task_id), db.get(Contract, dispute.contract_id)


def _execute_split(db: Session, dispute: Dispute, task: Task, contract: Contract,
                   share_bps: int, status: str, reason: str = "") -> None:
    dispute.split_base_cents = contract.amount_cents - contract.released_cents  # DSP-008 复核基数
    contract.frozen = False
    contract_service.execute_verdict(db, contract, share_bps)
    dispute.status = status
    dispute.verdict_executor_share_bps = share_bps
    dispute.verdict_reason = reason
    dispute.resolved_at = utcnow()
    db.add(dispute)
    transition(db, task, "completed" if share_bps > 0 else "cancelled")
    publish(db, "dispute.resolved", {"dispute_id": dispute.id, "task_id": task.id})


@router.post("/disputes/{dispute_id}/settlement")
def propose_settlement(
    dispute_id: int, body: ShareIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """DSP-004 和解提案：一方提出分割比例，另一方接受即执行。"""
    dispute, task, _ = _get_dispute(db, dispute_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    if dispute.status != "open":
        raise conflict("纠纷已结案", "dispute_closed")
    dispute.settlement_proposal = {"executor_share_bps": body.executor_share_bps, "proposed_by": user.id}
    db.add(dispute)
    return _dump(dispute)


@router.post("/disputes/{dispute_id}/settlement/accept")
def accept_settlement(
    dispute_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    dispute, task, contract = _get_dispute(db, dispute_id)
    proposal = dispute.settlement_proposal
    if not proposal:
        raise conflict("没有待接受的和解提案", "no_proposal")
    if user.id not in (task.creator_id, task.executor_id) or user.id == proposal["proposed_by"]:
        raise forbidden("需由对方接受提案")
    if dispute.status != "open":
        raise conflict("纠纷已结案", "dispute_closed")
    _execute_split(db, dispute, task, contract, proposal["executor_share_bps"], "settled", "双方和解")
    return _dump(dispute)


@router.post("/disputes/{dispute_id}/verdict")
def issue_verdict(
    dispute_id: int, body: ShareIn, arbiter: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """DSP-006/007 平台仲裁：裁决自动执行分账 + 败诉方信用惩罚（CRED-004）。"""
    dispute, task, contract = _get_dispute(db, dispute_id)
    if dispute.status != "open":
        raise conflict("纠纷已结案", "dispute_closed")
    if not body.reason:
        raise conflict("裁决必须给出理由（引用平台规则条款）", "reason_required")
    dispute.arbiter_id = arbiter.id
    _execute_split(db, dispute, task, contract, body.executor_share_bps, "resolved", body.reason)
    # 败诉方信用惩罚：比例低于 50% 视为执行者败诉，反之发布者败诉
    loser = task.executor_id if body.executor_share_bps < 5000 else task.creator_id
    credit.adjust_credit(db, loser, credit.CREDIT_DISPUTE_LOSER)
    from app.modules.admin.router import record_audit

    record_audit(db, arbiter.id, "dispute_verdict", "dispute", dispute.id,
                 f"执行者分成 {body.executor_share_bps}bps：{body.reason[:200]}")
    return _dump(dispute)


@router.post("/disputes/{dispute_id}/appeal")
def appeal(dispute_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """DSP-008 申诉复核：仅仲裁结案可申诉一次，升级高级仲裁员复核。"""
    dispute, task, _ = _get_dispute(db, dispute_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    if dispute.status != "resolved":
        raise conflict("仅平台仲裁结案的纠纷可申诉（和解结案不可申诉）", "not_appealable")
    if dispute.appealed:
        raise conflict("申诉机会已用完（每案一次）", "already_appealed")
    # DSP-010 申诉窗口：逾期裁决终局（业界惯例，防裁决永不生效）
    from datetime import timedelta

    from app.core.config import settings

    if dispute.resolved_at and utcnow() > dispute.resolved_at + timedelta(
        days=settings.APPEAL_WINDOW_DAYS
    ):
        raise conflict("申诉期已过，裁决已终局", "appeal_window_closed")
    dispute.appealed = True
    dispute.status = "appealed"
    db.add(dispute)
    return _dump(dispute) | {"appealed": True}


@router.post("/disputes/{dispute_id}/appeal-verdict")
def appeal_verdict(
    dispute_id: int, body: ShareIn, senior: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """高级仲裁员复核终局：与原裁决的差额做纠正性划转（原分账不回滚，差额多退少补）。"""
    from app.modules.wallet import service as wallet

    dispute, task, contract = _get_dispute(db, dispute_id)
    if dispute.status != "appealed":
        raise conflict("纠纷不在申诉复核中", "not_in_appeal")
    if not body.reason:
        raise conflict("复核裁决必须给出理由", "reason_required")
    old_share = dispute.split_base_cents * (dispute.verdict_executor_share_bps or 0) // 10000
    new_share = dispute.split_base_cents * body.executor_share_bps // 10000
    delta = new_share - old_share
    if delta > 0:
        wallet.transfer(db, task.creator_id, task.executor_id, delta, contract.id, "申诉复核补付")
    elif delta < 0:
        wallet.transfer(db, task.executor_id, task.creator_id, -delta, contract.id, "申诉复核退回")
    dispute.verdict_executor_share_bps = body.executor_share_bps
    dispute.verdict_reason = f"[复核终局] {body.reason}"
    dispute.arbiter_id = senior.id
    dispute.status = "resolved"
    db.add(dispute)
    publish(db, "dispute.resolved", {"dispute_id": dispute.id, "task_id": task.id, "appeal": True})
    from app.modules.admin.router import record_audit

    record_audit(db, senior.id, "dispute_appeal_verdict", "dispute", dispute.id,
                 f"复核终局 {body.executor_share_bps}bps，纠正 {delta} 分")
    return _dump(dispute) | {"corrective_delta_cents": delta}


@router.post("/disputes/jobs/escalate-overdue")
def run_escalate_overdue(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """DSP-009 纠纷 SLA job：开立超期未结案的纠纷自动升级。

    纠纷冻结着托管资金，业界（支付宝/Upwork）对处理时限有硬性 SLA——
    超期自动进人审队列：标记 escalated + 通知全体管理员 + 生成客服工单，
    幂等（已升级的不重复）。不做自动裁决：资金裁决必须有人类经手。
    """
    from datetime import timedelta

    from app.core.config import settings
    from app.modules.notification.service import notify
    from app.modules.support.models import Ticket

    cutoff = utcnow() - timedelta(days=settings.DISPUTE_SLA_DAYS)
    rows = (
        db.query(Dispute)
        .filter(Dispute.status == "open", Dispute.escalated.is_(False),
                Dispute.created_at <= cutoff)
        .all()
    )
    admins = db.query(User).filter(User.is_admin.is_(True)).all()
    for d in rows:
        d.escalated = True
        db.add(d)
        db.add(Ticket(
            user_id=d.opened_by, subject=f"[SLA超期] 纠纷 #{d.id} 超 {settings.DISPUTE_SLA_DAYS} 天未结案",
            body=f"任务 #{d.task_id} / 合约 #{d.contract_id}：{d.reason[:200]}。托管资金冻结中，请优先仲裁。",
        ))
        for a in admins:
            notify(db, a.id, "dispute", "纠纷处理超期升级",
                   f"纠纷 #{d.id}（任务 #{d.task_id}）已超 {settings.DISPUTE_SLA_DAYS} 天未结案，"
                   "托管资金冻结中，已进入人审队列。")
    return {"escalated": len(rows)}


@router.get("/disputes/{dispute_id}")
def get_dispute(dispute_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dispute, task, _ = _get_dispute(db, dispute_id)
    if user.id not in (task.creator_id, task.executor_id) and not user.is_admin:
        raise forbidden()
    return _dump(dispute)
