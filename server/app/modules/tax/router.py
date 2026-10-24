"""TAX-021~024 代扣明细、缴库、开票与台账。"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.locks import job_slot
from app.modules.account.models import User, utcnow

from . import service
from .models import InvoiceRequest
from app.core.timefmt import iso
from app.core.admin_roles import require_role

router = APIRouter(prefix="/finance", tags=["tax"])


@router.get("/my-tax")
def my_tax(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """TAX-021 我的代扣明细与年度合计。"""
    return service.my_summary(db, user.id)


@router.post("/jobs/remit-tax")
def remit_tax(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
              __=Depends(job_slot("remit_tax"), scope="function")):
    """TAX-013 代扣税款缴库。"""
    return service.remit(db)


def _remit_row(r) -> dict:
    # PAY-042f（291 号 spec）等了几天：等确认的算到现在，处理过的算到处理时
    waited = ((r.decided_at or utcnow()) - r.created_at).days
    return {"id": r.id, "amount_cents": r.amount_cents, "status": r.status, "decided_by": r.decided_by,
            "decision_reason": r.decision_reason, "created_at": iso(r.created_at), "decided_at": iso(r.decided_at),
            "waited_days": waited}


@router.get("/tax-remits")
def tax_remits(status: str = Query(default="awaiting_confirm", pattern="^(awaiting_confirm|remitted|rejected)$"),
               admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function")):
    """PAY-042d（287 号 spec）缴库草稿：默认列等确认的。"""
    from .models import TaxRemitRequest

    rows = (db.query(TaxRemitRequest).filter(TaxRemitRequest.status == status)
            .order_by(TaxRemitRequest.id.desc()).limit(100).all())
    return [_remit_row(r) for r in rows]


def _pending_remit(db: Session, request_id: int):
    from .models import TaxRemitRequest

    req = db.query(TaxRemitRequest).filter(TaxRemitRequest.id == request_id).with_for_update().first()
    if req is None:
        raise not_found("没有这笔缴库草稿")
    if req.status != "awaiting_confirm":
        raise conflict("这笔缴库草稿已经处理过了", "tax_remit_already_decided")
    return req


class RemitDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=200)


@router.post("/tax-remits/{request_id}/confirm")
def confirm_tax_remit(request_id: int, admin: User = Depends(require_role("finance")),
                      db: Session = Depends(get_db, scope="function")):
    """财务核对申报数后确认：只划草稿上的那个数（人看过的数），之后新代扣的留到下一次。"""
    from app.modules.admin.router import record_audit
    from app.modules.wallet import service as wallet

    req = _pending_remit(db, request_id)
    acct = wallet.get_or_create(db, service.TAX_USER_ID)
    if acct.available_cents < req.amount_cents:
        raise conflict(f"专户余额 ¥{acct.available_cents / 100:.2f} 不足草稿上的 ¥{req.amount_cents / 100:.2f}："
                       "请先查对账（代扣与缴库流水），驳回这份草稿后等下一次重新生成", "tax_remit_insufficient")
    service.remit_amount(db, acct, req.amount_cents)
    req.status, req.decided_by, req.decided_at = "remitted", admin.id, utcnow()
    record_audit(db, admin.id, "tax_remit_confirm", "tax_remit", req.id, f"确认缴库 {req.amount_cents} 分")
    return {**_remit_row(req), "balance_cents": acct.available_cents}


@router.post("/tax-remits/{request_id}/reject")
def reject_tax_remit(request_id: int, body: RemitDecisionIn, admin: User = Depends(require_role("finance")),
                     db: Session = Depends(get_db, scope="function")):
    """对不上就驳回（要写原因）：不动钱，下一次缴库 job 按当时的余额重新生成草稿。"""
    from app.modules.admin.router import record_audit

    req = _pending_remit(db, request_id)
    if len(body.reason.strip()) < 2:
        raise bad_request("驳回缴库草稿要写明哪里对不上", "reason_required")
    req.status, req.decided_by, req.decided_at = "rejected", admin.id, utcnow()
    req.decision_reason = body.reason.strip()
    record_audit(db, admin.id, "tax_remit_reject", "tax_remit", req.id,
                 f"驳回缴库草稿 {req.amount_cents} 分：{req.decision_reason}")
    return _remit_row(req)


@router.post("/jobs/remind-tax-remits")
def run_remind_tax_remits(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                          __=Depends(job_slot("tax_remit_reminders"), scope="function")):
    """PAY-042f（291 号 spec）等确认太久的缴库草稿催财务。"""
    return service.remind_remits(db)


@router.get("/tax-ledger")
def tax_ledger(admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function")):
    """TAX-024 管理端代扣与缴库台账。"""
    return service.ledger(db)


class InvoiceIn(BaseModel):
    contract_id: int
    title: str = Field(min_length=2, max_length=120)
    tax_no: str = Field(default="", max_length=40)


@router.post("/invoices", status_code=201)
def request_invoice(body: InvoiceIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db, scope="function")):
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
def my_invoices(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = (
        db.query(InvoiceRequest)
        .filter(InvoiceRequest.requester_id == user.id)
        .order_by(InvoiceRequest.id.desc())
        .all()
    )
    return [
        {"id": r.id, "kind": r.kind, "contract_id": r.contract_id,
         "amount_cents": r.amount_cents, "title": r.title, "status": r.status,
         "note": r.note, "at": iso(r.created_at)}
        for r in rows
    ]
