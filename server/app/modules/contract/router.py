from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden, not_found
from app.modules.account.models import User
from app.modules.task.models import Task
from app.modules.task.service import transition

from . import service
from .models import Contract

router = APIRouter(prefix="/contracts", tags=["contract"])


def _get(db: Session, contract_id: int, user: User) -> Contract:
    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return contract


def _dump(c: Contract) -> dict:
    return {
        "id": c.id,
        "task_id": c.task_id,
        "requester_id": c.requester_id,
        "executor_id": c.executor_id,
        "amount_cents": c.amount_cents,
        "fee_bps": c.fee_bps,
        "terms": c.terms,
        "status": c.status,
        "signed_by_requester": c.signed_by_requester,
        "signed_by_executor": c.signed_by_executor,
        "frozen": c.frozen,
    }


@router.get("/by-task/{task_id}")
def get_contract_by_task(
    task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = db.query(Contract).filter(Contract.task_id == task_id).first()
    if not contract:
        raise not_found("该任务暂无合约")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    return _dump(contract)


@router.get("/{contract_id}")
def get_contract(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return _dump(_get(db, contract_id, user))


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
