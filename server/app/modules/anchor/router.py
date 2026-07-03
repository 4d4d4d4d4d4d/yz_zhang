from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import forbidden
from app.modules.account.models import User
from app.modules.contract.models import Contract

from . import service
from .models import AnchorEntry

router = APIRouter(prefix="/anchors", tags=["anchor"])


@router.get("/verify")
def verify(db: Session = Depends(get_db)):
    """SC-011 全链完整性校验（公开可验证）。"""
    return service.verify_chain(db)


@router.get("/contracts/{contract_id}")
def contract_anchors(
    contract_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    contract = db.get(Contract, contract_id)
    if not contract:
        return []
    if user.id not in (contract.requester_id, contract.executor_id) and not user.is_admin:
        raise forbidden()
    rows = (
        db.query(AnchorEntry)
        .filter(AnchorEntry.ref_type == "contract", AnchorEntry.ref_id == contract_id)
        .order_by(AnchorEntry.seq)
        .all()
    )
    return [
        {"seq": r.seq, "event_type": r.event_type, "chain_hash": r.chain_hash,
         "payload_hash": r.payload_hash, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
