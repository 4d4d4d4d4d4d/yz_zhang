"""TAX-021~024 代扣明细、缴库、开票与台账。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_job_auth
from app.core.errors import bad_request, forbidden, not_found
from app.core.locks import job_slot
from app.modules.account.models import User

from . import service
from .models import InvoiceRequest

router = APIRouter(prefix="/finance", tags=["tax"])


@router.get("/my-tax")
def my_tax(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """TAX-021 我的代扣明细与年度合计。"""
    return service.my_summary(db, user.id)


@router.post("/jobs/remit-tax")
def remit_tax(db: Session = Depends(get_db), _=Depends(require_job_auth),
              __=Depends(job_slot("remit_tax"))):
    """TAX-013 代扣税款缴库。"""
    return service.remit(db)


@router.get("/tax-ledger")
def tax_ledger(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """TAX-024 管理端代扣与缴库台账。"""
    return service.ledger(db)


class InvoiceIn(BaseModel):
    contract_id: int
    title: str = Field(min_length=2, max_length=120)
    tax_no: str = Field(default="", max_length=40)


@router.post("/invoices", status_code=201)
def request_invoice(body: InvoiceIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """TAX-022 申请开具**平台服务费**发票。

    只开平台佣金那部分：执行者的劳务报酬平台没有开票资格，
    那部分要么由执行者自己开、要么走代开渠道（TAX-023）。
    含糊其辞地"帮你开全额发票"是虚开，不是服务。
    """
    from app.modules.contract.models import Contract

    contract = db.get(Contract, body.contract_id)
    if not contract:
        raise not_found("合约不存在")
    if user.id != contract.requester_id:
        raise forbidden("仅发布方可申请平台服务费发票", "not_party")
    if contract.status not in ("released", "split"):
        raise bad_request("合约完成放款后方可开票", "not_settled")
    fee = contract.amount_cents * contract.fee_bps // 10000
    if fee <= 0:
        raise bad_request("本合约无平台服务费", "no_fee")
    existing = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.contract_id == contract.id,
                InvoiceRequest.kind == "platform_fee",
                InvoiceRequest.status != "rejected")
        .first()
    )
    if existing:
        raise bad_request("该合约已申请过平台服务费发票", "already_requested")
    row = InvoiceRequest(
        kind="platform_fee", requester_id=user.id, contract_id=contract.id,
        amount_cents=fee, title=body.title, tax_no=body.tax_no,
        note="平台服务费（技术服务/信息服务），不含执行方劳务报酬",
    )
    db.add(row)
    db.flush()
    return {
        "id": row.id, "kind": row.kind, "amount_cents": fee, "status": row.status,
        "scope_note": "本发票仅覆盖平台服务费；执行方劳务报酬需由执行方或代开渠道开具",
    }


@router.get("/invoices")
def my_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.requester_id == user.id)
        .order_by(InvoiceRequest.id.desc())
        .all()
    )
    return [
        {"id": r.id, "kind": r.kind, "contract_id": r.contract_id,
         "amount_cents": r.amount_cents, "title": r.title, "status": r.status,
         "note": r.note, "at": r.created_at.isoformat()}
        for r in rows
    ]
