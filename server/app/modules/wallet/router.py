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


class PayoutAccountIn(BaseModel):
    kind: str = Field(default="bank", pattern="^(bank|alipay)$")
    account_no: str = Field(min_length=6, max_length=64)
    holder_name: str = Field(min_length=2, max_length=50)


def _mask(no: str) -> str:
    return no[:4] + "****" + no[-4:] if len(no) >= 8 else "****"


@router.get("/payout-account")
def get_payout_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import PayoutAccount

    acct = db.get(PayoutAccount, user.id)
    if not acct:
        return {"bound": False}
    return {"bound": True, "kind": acct.kind, "account_no": _mask(acct.account_no),
            "holder_name": acct.holder_name}


@router.put("/payout-account")
def bind_payout_account(
    body: PayoutAccountIn, user: User = Depends(require_verified), db: Session = Depends(get_db)
):
    """PAY-005 绑定收款账户：实名后可绑；收款人须与实名一致（防代提/洗钱）。"""
    from app.core.errors import bad_request

    from .models import PayoutAccount

    if user.real_name and body.holder_name != user.real_name:
        raise bad_request("收款人姓名须与实名认证一致", "holder_name_mismatch")
    # LAW-031 收款账户是敏感个人信息：绑定行为即构成对该项的单独同意
    from app.modules.legal import consent

    consent.ensure(db, user.id, "payment")
    # AML-013 收款账户聚集：只标记不拦截——夫妻共用一张卡、帮父母代收都是真实场景
    from app.modules.aml import service as aml

    aml.check_payout_clustering(db, user.id, body.account_no)
    acct = db.get(PayoutAccount, user.id)
    if not acct:
        acct = PayoutAccount(user_id=user.id)
    acct.kind = body.kind
    acct.account_no = body.account_no
    acct.holder_name = body.holder_name
    db.add(acct)
    return {"bound": True, "kind": acct.kind, "account_no": _mask(acct.account_no)}


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
    """PAY-001 / VND-011 充值：两阶段（下单 → 供应商确认 → 才入账）。

    走 `PaymentProvider` 抽象：模拟通道即时确认（开发体验不变），
    真实通道返回 pending + 支付链接，等回调 `/wallet/pay/callback` 入账。
    资金操作强制幂等（14.6/05.B）：同一 Idempotency-Key 重复提交只入账一次。
    """
    from app.vendors import payment_service
    from app.vendors.base import VendorError

    def run():
        try:
            return payment_service.create_topup_order(db, user.id, body.amount_cents)
        except VendorError as exc:
            raise exc.as_http() from exc

    return replay_or_run(db, user.id, idempotency_key or None, "wallet.topup", run,
                         params={"amount_cents": body.amount_cents})


class PayCallbackIn(BaseModel):
    """VND-012 支付回调报文（模拟通道形态；真实通道字段由供应商定义）。"""

    order_no: str
    amount_cents: int
    external_ref: str = ""
    sign: str


@router.post("/pay/callback")
def pay_callback(body: PayCallbackIn, db: Session = Depends(get_db)):
    """VND-012 支付回调：验签 → 幂等确认入账。**无需登录**（供应商侧调用），
    因此验签是唯一信任来源：签名不通过一律拒绝，不看金额也不查订单。"""
    from app.vendors import payment_service
    from app.vendors.base import VendorError

    payload = body.model_dump(exclude={"sign"})
    try:
        return payment_service.handle_callback(db, payload, body.sign)
    except VendorError as exc:
        raise exc.as_http() from exc


@router.post("/withdraw")
def withdraw(
    body: AmountIn, user: User = Depends(require_verified), db: Session = Depends(get_db),
    idempotency_key: str = Header(default=""),
):
    """PAY-004/007 提现：小额即时（模拟 T+0），大额冻结人审，日限额硬拒。幂等防重复。"""
    from app.modules.legal import consent

    consent.require_current_agreement(db, user.id)  # LAW-030
    # LAW-031 支付项的「未同意」不在这里拦：撤回时收款账户已被解绑，
    # 下面的 no_payout_account 校验既覆盖了这种情况，提示也更有用

    def run():
        return service.withdraw(db, user.id, body.amount_cents)

    return replay_or_run(db, user.id, idempotency_key or None, "wallet.withdraw", run,
                         params={"amount_cents": body.amount_cents})


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
    result = service.decide_withdraw(db, req, approve=True, admin_id=admin.id)
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "withdraw_approve", "withdraw_request", request_id,
                 f"批准提现 {req.amount_cents} 分")
    return result


@router.post("/withdraw-requests/{request_id}/reject")
def reject_withdraw(
    request_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from .models import WithdrawRequest

    req = db.get(WithdrawRequest, request_id)
    if not req:
        from app.core.errors import not_found

        raise not_found("提现申请不存在")
    result = service.decide_withdraw(db, req, approve=False, admin_id=admin.id)
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, "withdraw_reject", "withdraw_request", request_id,
                 f"驳回提现 {req.amount_cents} 分")
    return result


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
