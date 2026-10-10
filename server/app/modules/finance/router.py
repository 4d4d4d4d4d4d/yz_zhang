"""FIN-042 资金流向审计 API。

任一笔钱都能回溯到「谁付的 → 存管流水号 → 分账指令 → 谁收的」，
缺任一环即告警。合约当事人可查自己那份，管理员可查全部。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import forbidden, not_found
from app.modules.account.models import User
from app.modules.contract.models import Contract

from . import service

router = APIRouter(tags=["finance"])


@router.get("/contracts/{contract_id}/settlements")
def contract_settlements(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """一份合约上发生过的全部分账指令（当事人与管理员可见）。"""
    contract = db.get(Contract, contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    from app.vendors.ledger import is_sandbox

    return {"settlements": service.contract_trail(db, contract_id),
            "sandbox": is_sandbox()}


@router.get("/admin/settlements/verify")
def verify_settlements(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """FIN-060 分账守恒校验（同时并入日终对账）。"""
    problems = service.verify_conservation(db)
    return {"ok": not problems, "problems": problems}
