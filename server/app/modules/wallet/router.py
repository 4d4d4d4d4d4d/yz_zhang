from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_verified
from app.core.idempotency import replay_or_run
from app.modules.account.models import User

from . import service
from .models import LedgerEntry

router = APIRouter(prefix="/wallet", tags=["wallet"])


class AmountIn(BaseModel):
    amount_cents: int = Field(gt=0)


@router.get("")
def get_wallet(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    acct = service.get_or_create(db, user.id)
    return {
        "available_cents": acct.available_cents,
        "escrow_cents": acct.escrow_cents,
        "frozen_cents": acct.frozen_cents,
    }


@router.post("/topup")
def topup(
    body: AmountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
    idempotency_key: str = Header(default=""),
):
    """PAY-001 支付通道的开发模拟：直接入账。生产接微信/支付宝回调。

    资金操作强制幂等（14.6/05.B）：同一 Idempotency-Key 重复提交只入账一次。
    """
    def run():
        acct = service.topup(db, user.id, body.amount_cents)
        return {"available_cents": acct.available_cents}

    return replay_or_run(db, user.id, idempotency_key or None, "wallet.topup", run)


@router.post("/withdraw")
def withdraw(
    body: AmountIn, user: User = Depends(require_verified), db: Session = Depends(get_db),
    idempotency_key: str = Header(default=""),
):
    """PAY-004/007 提现：小额即时（模拟 T+0），大额冻结人审，日限额硬拒。幂等防重复。"""
    def run():
        return service.withdraw(db, user.id, body.amount_cents)

    return replay_or_run(db, user.id, idempotency_key or None, "wallet.withdraw", run)


# ---------- PAY-007 大额提现人审（管理端） ----------
@router.get("/withdraw-requests")
def list_withdraw_requests(
    status: str = "pending",
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from .models import WithdrawRequest

    rows = (
        db.query(WithdrawRequest).filter(WithdrawRequest.status == status)
        .order_by(WithdrawRequest.id).limit(200).all()
    )
    return [
        {"id": r.id, "user_id": r.user_id, "amount_cents": r.amount_cents,
         "status": r.status, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.post("/withdraw-requests/{request_id}/approve")
def approve_withdraw(
    request_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from .models import WithdrawRequest

    req = db.get(WithdrawRequest, request_id)
    if not req:
        from app.core.errors import not_found

        raise not_found("提现申请不存在")
    return service.decide_withdraw(db, req, approve=True, admin_id=admin.id)


@router.post("/withdraw-requests/{request_id}/reject")
def reject_withdraw(
    request_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from .models import WithdrawRequest

    req = db.get(WithdrawRequest, request_id)
    if not req:
        from app.core.errors import not_found

        raise not_found("提现申请不存在")
    return service.decide_withdraw(db, req, approve=False, admin_id=admin.id)


@router.get("/ledger")
def ledger(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(LedgerEntry)
        .filter(LedgerEntry.user_id == user.id)
        .order_by(LedgerEntry.id.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "amount_cents": r.amount_cents,
            "contract_id": r.contract_id,
            "memo": r.memo,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
