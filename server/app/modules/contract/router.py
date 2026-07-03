from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User
from app.modules.task.models import Task
from app.modules.task.service import transition

from pydantic import BaseModel, Field

from . import service
from .models import ChangeOrder, Contract, Milestone

router = APIRouter(prefix="/contracts", tags=["contract"])


class MilestonesIn(BaseModel):
    items: list[dict]  # [{title, amount_cents}]


class ChangeIn(BaseModel):
    new_amount_cents: int = Field(gt=0)
    reason: str = ""


def _get(db: Session, contract_id: int, user: User) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return contract


def _dump(c: Contract, db: Session | None = None) -> dict:
    out = {
        "id": c.id,
        "task_id": c.task_id,
        "requester_id": c.requester_id,
        "executor_id": c.executor_id,
        "amount_cents": c.amount_cents,
        "released_cents": c.released_cents,
        "fee_bps": c.fee_bps,
        "terms": c.terms,
        "status": c.status,
        "signed_by_requester": c.signed_by_requester,
        "signed_by_executor": c.signed_by_executor,
        "frozen": c.frozen,
        "version": c.version,
        "deposit_cents": c.deposit_cents,
        "deposit_status": c.deposit_status,
    }
    if db is not None:
        rows = (
            db.query(Milestone).filter(Milestone.contract_id == c.id).order_by(Milestone.idx).all()
        )
        out["milestones"] = [
            {"idx": m.idx, "title": m.title, "amount_cents": m.amount_cents, "status": m.status}
            for m in rows
        ]
    return out


@router.get("/by-task/{task_id}")
def get_contract_by_task(
    task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract:
        raise not_found("该任务暂无合约")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return _dump(contract, db)


@router.get("/{contract_id}")
def get_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _dump(_get(db, contract_id, user), db)


# ---------- SC-004 里程碑 ----------
def _milestone(db: Session, contract: Contract, idx: int) -> Milestone:
    m = (
        db.query(Milestone)
        .filter(Milestone.contract_id == contract.id, Milestone.idx == idx)
        .first()
    )
    if not m:
        raise not_found("里程碑不存在")
    return m


@router.post("/{contract_id}/milestones")
def define_milestones(
    contract_id: int, body: MilestonesIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    service.define_milestones(db, contract, user.id, body.items)
    return _dump(contract, db)


@router.post("/{contract_id}/milestones/{idx}/deliver")
def deliver_milestone(
    contract_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    service.deliver_milestone(db, contract, user.id, _milestone(db, contract, idx))
    return _dump(contract, db)


@router.post("/{contract_id}/milestones/{idx}/accept")
def accept_milestone(
    contract_id: int, idx: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    service.release_milestone(db, contract, user.id, _milestone(db, contract, idx))
    # 末期放款 → 任务闭环（状态机按白名单两步走）
    if contract.status == "released":
        from app.modules.account import service as credit

        task = db.get(Task, contract.task_id)
        if task and task.status != "completed":
            if task.status == "in_progress":
                transition(db, task, "pending_acceptance")
            if task.status == "pending_acceptance":
                from app.modules.account.models import utcnow

                task.completed_at = utcnow()
                transition(db, task, "completed")
                if task.executor_id:
                    credit.record_task_completed(db, task.executor_id)
    return _dump(contract, db)


# ---------- SC-007 变更单 ----------
@router.post("/{contract_id}/change-orders", status_code=201)
def propose_change(
    contract_id: int, body: ChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    order = service.propose_change(db, contract, user.id, body.new_amount_cents, body.reason)
    return {"id": order.id, "status": order.status, "new_amount_cents": order.new_amount_cents}


@router.post("/{contract_id}/change-orders/{order_id}/accept")
def accept_change(
    contract_id: int, order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    order = db.get(ChangeOrder, order_id)
    if not order or order.contract_id != contract.id:
        raise not_found("变更单不存在")
    service.accept_change(db, contract, user.id, order)
    return _dump(contract, db)


@router.post("/{contract_id}/change-orders/{order_id}/reject")
def reject_change(
    contract_id: int, order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    order = db.get(ChangeOrder, order_id)
    if not order or order.contract_id != contract.id:
        raise not_found("变更单不存在")
    if order.status != "pending":
        raise not_found("变更单已处理")
    if user.id == order.proposed_by:
        raise forbidden("提案方不能自行处理")
    order.status = "rejected"
    db.add(order)
    return {"id": order.id, "status": "rejected"}


@router.post("/{contract_id}/sign")
def sign_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    return _dump(service.sign(db, contract, user.id))


@router.post("/{contract_id}/fund")
def fund_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = _get(db, contract_id, user)
    service.fund(db, contract, user.id)
    # 资金托管完成 → 任务进入执行中（03 状态机联动）
    task = db.get(Task, contract.task_id)
    transition(db, task, "in_progress")
    return _dump(contract)
