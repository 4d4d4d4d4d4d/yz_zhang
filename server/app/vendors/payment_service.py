"""VND-011~013 支付编排：两阶段充值、回调入账、提现打款。

**关键不变量**：钱包余额只在 `PaymentOrder` 由 pending 变为 succeeded 的
那一次转移中增加，且同一订单只发生一次。回调重放、金额不符、验签失败
都不得改变余额。
"""
import uuid

from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, not_found
from app.core.locks import lock_wallets
from app.modules.account.models import utcnow

from . import base
from .models import PaymentOrder
from .payment import sign_callback
from .registry import get_provider


def _order_no() -> str:
    return f"TP{utcnow():%Y%m%d}{uuid.uuid4().hex[:12]}"


def create_topup_order(db: Session, user_id: int, amount_cents: int) -> dict:
    """VND-011 阶段一：下单。此刻**不动余额**。

    模拟通道会即时返回 succeeded，于是紧接着走确认入账——
    对开发体验与既有测试无感，但结构已是真实支付的两阶段形态。
    """
    base.require_amount(amount_cents)
    provider = get_provider("payment")
    order = PaymentOrder(
        order_no=_order_no(), user_id=user_id, amount_cents=amount_cents,
        provider=provider.name, status="pending",
    )
    db.add(order)
    db.flush()

    result = base.call(
        db, "payment", provider.name, "create_charge",
        {"order_no": order.order_no, "amount_cents": amount_cents},
        lambda: provider.create_charge(order.order_no, amount_cents, "账户充值"),
        idem_key=f"charge:{order.order_no}",
    )
    order.external_ref = result.external_ref
    db.add(order)
    db.flush()

    if result.status == "succeeded":
        return confirm_topup(db, order.order_no, amount_cents, result.external_ref)
    return {
        "order_no": order.order_no, "status": "pending",
        "pay_url": result.data.get("pay_url", ""),
    }


def confirm_topup(db: Session, order_no: str, amount_cents: int, external_ref: str = "") -> dict:
    """VND-011/012 阶段二：确认到账并入账。**幂等**且**校验金额**。

    - 订单已 succeeded → 直接回放，不重复加钱（回调重放攻击的主要防线）
    - 回调金额与订单金额不符 → 标记 mismatch 并挂起人工，绝不按回调金额入账
    """
    from app.modules.wallet import service as wallet

    order = db.query(PaymentOrder).filter(PaymentOrder.order_no == order_no).first()
    if not order:
        raise not_found("支付订单不存在", "order_not_found")
    if order.status == "succeeded":
        acct = wallet.get_or_create(db, order.user_id)
        return {"order_no": order_no, "status": "succeeded", "replayed": True,
                "available_cents": acct.available_cents}
    if order.status == "mismatch":
        raise conflict("该订单金额存在异常，已挂起人工处理", "order_mismatch")
    if amount_cents != order.amount_cents:
        _flag_mismatch(order.order_no)
        raise bad_request("回调金额与订单金额不一致，已挂起人工核对", "amount_mismatch")

    lock_wallets(db, order.user_id)
    acct = wallet.topup(db, order.user_id, order.amount_cents)
    order.status = "succeeded"
    order.paid_at = utcnow()
    if external_ref:
        order.external_ref = external_ref
    db.add(order)
    db.flush()
    return {"order_no": order_no, "status": "succeeded",
            "available_cents": acct.available_cents}


def _flag_mismatch(order_no: str) -> None:
    """把 mismatch 标记落在**独立事务**里。

    请求会因随后的 400 被 `get_db` 整体回滚——若沿用同一会话，
    这个「已发现异常」的事实会跟着一起消失，运营再也看不到它。
    """
    from app.core.db import SessionLocal

    with SessionLocal() as side:
        row = side.query(PaymentOrder).filter(PaymentOrder.order_no == order_no).first()
        if row and row.status == "pending":
            row.status = "mismatch"
            side.add(row)
            side.commit()


def handle_callback(db: Session, payload: dict, signature: str) -> dict:
    """VND-012 支付回调入口：先验签，再确认入账。

    验签失败一律拒绝——不看金额、不查订单，避免把未验证输入当事实。
    """
    provider = get_provider("payment")
    if not provider.verify_callback(payload, signature):
        raise bad_request("回调签名校验失败", "invalid_signature")
    order_no = str(payload.get("order_no", ""))
    amount = int(payload.get("amount_cents", -1))
    if not order_no or amount < 0:
        raise bad_request("回调参数不完整", "invalid_payload")
    return confirm_topup(db, order_no, amount, str(payload.get("external_ref", "")))


def make_signature(payload: dict) -> str:
    """测试与模拟通道构造合法回调用；生产由供应商侧签名。"""
    return sign_callback(payload)


def send_payout(db: Session, user_id: int, amount_cents: int, ref: str) -> str:
    """VND-013 提现打款：返回外部单号，失败抛 VendorError 由调用方回滚。"""
    from app.modules.wallet.models import PayoutAccount

    provider = get_provider("payment")
    acct = db.get(PayoutAccount, user_id)
    if not acct:
        raise bad_request("请先绑定收款账户", "no_payout_account")
    result = base.call(
        db, "payment", provider.name, "create_payout",
        {"order_no": ref, "amount_cents": amount_cents, "account_no": acct.account_no},
        lambda: provider.create_payout(
            ref, {"kind": acct.kind, "account_no": acct.account_no,
                  "holder_name": acct.holder_name}, amount_cents,
        ),
        idem_key=f"payout:{ref}",
    )
    return result.external_ref
