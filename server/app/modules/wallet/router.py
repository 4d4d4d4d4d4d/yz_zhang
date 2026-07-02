from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_verified
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
def topup(body: AmountIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """PAY-001 支付通道的开发模拟：直接入账。生产接微信/支付宝回调。"""
    acct = service.topup(db, user.id, body.amount_cents)
    return {"available_cents": acct.available_cents}


@router.post("/withdraw")
def withdraw(body: AmountIn, user: User = Depends(require_verified), db: Session = Depends(get_db)):
    """PAY-004 提现：实名后可提（模拟 T+0 到账）。"""
    acct = service.withdraw(db, user.id, body.amount_cents)
    return {"available_cents": acct.available_cents}


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
