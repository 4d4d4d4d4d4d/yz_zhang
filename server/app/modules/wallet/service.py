"""钱包核心操作。所有资金变动必须走这里并落流水（12.A 审计要求）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request

from .models import LedgerEntry, WalletAccount

PLATFORM_USER_ID = 0  # 平台佣金账户


def get_or_create(db: Session, user_id: int) -> WalletAccount:
    acct = db.get(WalletAccount, user_id)
    if not acct:
        acct = WalletAccount(user_id=user_id)
        db.add(acct)
        db.flush()
    return acct


def _log(db: Session, user_id: int, kind: str, amount: int, contract_id=None, memo=""):
    db.add(
        LedgerEntry(
            user_id=user_id, kind=kind, amount_cents=amount, contract_id=contract_id, memo=memo
        )
    )


def topup(db: Session, user_id: int, amount: int) -> WalletAccount:
    if amount <= 0:
        raise bad_request("充值金额必须为正", "invalid_amount")
    acct = get_or_create(db, user_id)
    acct.available_cents += amount
    _log(db, user_id, "topup", amount)
    return acct


def withdraw(db: Session, user_id: int, amount: int) -> WalletAccount:
    acct = get_or_create(db, user_id)
    if amount <= 0 or amount > acct.available_cents:
        raise bad_request("可用余额不足", "insufficient_balance")
    acct.available_cents -= amount
    _log(db, user_id, "withdraw", -amount)
    return acct


def escrow_hold(db: Session, user_id: int, amount: int, contract_id: int):
    """SC-003 资金托管：可用 → 托管。"""
    acct = get_or_create(db, user_id)
    if acct.available_cents < amount:
        raise bad_request("可用余额不足，请先充值", "insufficient_balance")
    acct.available_cents -= amount
    acct.escrow_cents += amount
    _log(db, user_id, "escrow_hold", -amount, contract_id, "合约资金托管")


def escrow_release(
    db: Session, payer_id: int, payee_id: int, amount: int, fee: int, contract_id: int
):
    """SC-005/SC-009 验收放款：托管 → 执行者可用（扣佣金）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < amount:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= amount
    payee = get_or_create(db, payee_id)
    payee.available_cents += amount - fee
    _log(db, payee_id, "escrow_release", amount - fee, contract_id, "任务验收放款")
    if fee > 0:
        platform = get_or_create(db, PLATFORM_USER_ID)
        platform.available_cents += fee
        _log(db, PLATFORM_USER_ID, "fee", fee, contract_id, "平台佣金")


def escrow_refund(db: Session, payer_id: int, amount: int, contract_id: int, memo="托管退款"):
    """SC-006 取消/违约退款：托管 → 发布者可用（原路退回的模拟）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < amount:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= amount
    payer.available_cents += amount
    _log(db, payer_id, "refund", amount, contract_id, memo)


def freeze_deposit(db: Session, user_id: int, amount: int, contract_id: int):
    """CRED-005 保证金冻结：可用 → 冻结。"""
    acct = get_or_create(db, user_id)
    if acct.available_cents < amount:
        raise bad_request("可用余额不足以缴纳保证金", "insufficient_deposit")
    acct.available_cents -= amount
    acct.frozen_cents += amount
    _log(db, user_id, "deposit_hold", -amount, contract_id, "任务保证金冻结")


def unfreeze_deposit(db: Session, user_id: int, amount: int, contract_id: int):
    """保证金退还：冻结 → 可用。"""
    acct = get_or_create(db, user_id)
    if acct.frozen_cents < amount:
        raise bad_request("冻结余额异常", "frozen_mismatch")
    acct.frozen_cents -= amount
    acct.available_cents += amount
    _log(db, user_id, "deposit_return", amount, contract_id, "保证金退还")


def forfeit_deposit(db: Session, executor_id: int, requester_id: int, amount: int, contract_id: int):
    """执行者违约：保证金罚没给发布者。"""
    acct = get_or_create(db, executor_id)
    if acct.frozen_cents < amount:
        raise bad_request("冻结余额异常", "frozen_mismatch")
    acct.frozen_cents -= amount
    _log(db, executor_id, "deposit_forfeit", -amount, contract_id, "违约保证金罚没")
    payee = get_or_create(db, requester_id)
    payee.available_cents += amount
    _log(db, requester_id, "deposit_forfeit", amount, contract_id, "对方违约保证金赔付")


def dispute_split(
    db: Session, payer_id: int, payee_id: int, total: int, payee_share: int, fee: int, contract_id: int
):
    """SC-008/DSP-007 仲裁分割：托管按裁决比例分给双方（佣金只对执行者所得部分收取）。"""
    payer = get_or_create(db, payer_id)
    if payer.escrow_cents < total:
        raise bad_request("托管余额异常", "escrow_mismatch")
    payer.escrow_cents -= total
    refund_part = total - payee_share
    if refund_part > 0:
        payer.available_cents += refund_part
        _log(db, payer_id, "dispute_split", refund_part, contract_id, "仲裁退回")
    if payee_share > 0:
        payee = get_or_create(db, payee_id)
        payee.available_cents += payee_share - fee
        _log(db, payee_id, "dispute_split", payee_share - fee, contract_id, "仲裁获得")
        if fee > 0:
            platform = get_or_create(db, PLATFORM_USER_ID)
            platform.available_cents += fee
            _log(db, PLATFORM_USER_ID, "fee", fee, contract_id, "平台佣金(仲裁)")
