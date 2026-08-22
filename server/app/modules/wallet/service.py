"""钱包核心操作。所有资金变动必须走这里并落流水（12.A 审计要求）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.core.locks import lock_wallets

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


def _today_withdrawn(db: Session, user_id: int) -> int:
    """当日已提现（含出账流水与待审冻结）总额，用于日限额（PAY-007）。"""
    from sqlalchemy import func

    from app.modules.account.models import utcnow

    from .models import WithdrawRequest

    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    done = -(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == user_id, LedgerEntry.kind == "withdraw",
                LedgerEntry.created_at >= day_start)
        .scalar()
    )
    pending = (
        db.query(func.coalesce(func.sum(WithdrawRequest.amount_cents), 0))
        .filter(WithdrawRequest.user_id == user_id, WithdrawRequest.status == "pending",
                WithdrawRequest.created_at >= day_start)
        .scalar()
    )
    return int(done) + int(pending)


def _send_payout(db: Session, user_id: int, amount: int, ref: str) -> str:
    """VND-013 打款出账：供应商失败直接抛出，由 get_db 整体回滚——
    宁可提现失败重来，也不能出现「账扣了钱没打出去」。"""
    from app.vendors import payment_service
    from app.vendors.base import VendorError

    try:
        return payment_service.send_payout(db, user_id, amount, ref)
    except VendorError as exc:
        raise exc.as_http() from exc


def withdraw(db: Session, user_id: int, amount: int) -> dict:
    """PAY-005/007 提现：须先绑收款账户；日限额硬拒；大额冻结进人审；小额即时出账。"""
    from app.core.config import settings
    from app.modules.account.models import utcnow

    from .models import PayoutAccount, WithdrawRequest

    if not db.get(PayoutAccount, user_id):  # PAY-005 提现前置：必须已绑收款账户
        raise bad_request("请先绑定收款账户", "no_payout_account")
    lock_wallets(db, user_id)  # CONC-012 并发提现必须串行，否则日限额与余额都能被绕过
    acct = get_or_create(db, user_id)
    if amount <= 0 or amount > acct.available_cents:
        raise bad_request("可用余额不足", "insufficient_balance")
    if _today_withdrawn(db, user_id) + amount > settings.WITHDRAW_DAILY_LIMIT_CENTS:
        raise bad_request(
            f"超出单日提现限额（{settings.WITHDRAW_DAILY_LIMIT_CENTS / 100:.0f} 元）",
            "daily_limit_exceeded",
        )
    if amount >= settings.LARGE_WITHDRAW_CENTS:
        # 大额：可用 → 冻结，生成人审申请（批准划出 / 驳回解冻）
        acct.available_cents -= amount
        acct.frozen_cents += amount
        req = WithdrawRequest(user_id=user_id, amount_cents=amount)
        db.add(req)
        db.flush()
        _log(db, user_id, "withdraw_hold", -amount, memo=f"大额提现待审 #{req.id}")
        return {"status": "pending_review", "request_id": req.id,
                "available_cents": acct.available_cents, "frozen_cents": acct.frozen_cents}
    acct.available_cents -= amount
    entry_ref = f"wd-{user_id}-{int(utcnow().timestamp() * 1000)}"
    payout_ref = _send_payout(db, user_id, amount, entry_ref)
    _log(db, user_id, "withdraw", -amount, memo=f"提现打款 {payout_ref}")
    return {"status": "done", "available_cents": acct.available_cents,
            "frozen_cents": acct.frozen_cents, "payout_ref": payout_ref}


def decide_withdraw(db: Session, req, approve: bool, admin_id: int) -> dict:
    """PAY-007 人审裁决：批准=冻结划出（落 withdraw 流水），驳回=解冻退回。"""
    from app.modules.account.models import utcnow

    if req.status != "pending":
        raise bad_request("该提现申请已处理", "request_closed")
    lock_wallets(db, req.user_id)  # CONC-012
    acct = get_or_create(db, req.user_id)
    acct.frozen_cents -= req.amount_cents
    if approve:
        payout_ref = _send_payout(db, req.user_id, req.amount_cents, f"wdreq-{req.id}")
        _log(db, req.user_id, "withdraw", -req.amount_cents,
             memo=f"大额提现批准 #{req.id} 打款 {payout_ref}")
        req.status = "approved"
    else:
        acct.available_cents += req.amount_cents
        _log(db, req.user_id, "withdraw_refund", req.amount_cents, memo=f"大额提现驳回退回 #{req.id}")
        req.status = "rejected"
    req.decided_by = admin_id
    req.decided_at = utcnow()
    db.add_all([acct, req])
    return {"status": req.status, "amount_cents": req.amount_cents}


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


def platform_finance(db: Session) -> dict:
    """SC-009/OPS-010 平台收入：以平台账户实际入账为唯一事实来源。

    佣金按每笔放款/裁决分账整数向下取整实收（含纠纷/取消场景），
    与「Σ released×费率」的估算口径不同——后者会漏计纠纷/取消佣金且有取整漂移。
    """
    from sqlalchemy import func

    platform = get_or_create(db, PLATFORM_USER_ID)
    # fee 流水为正数入账（见 escrow_release/dispute_split），直接求和即累计佣金
    total_fee = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee")
        .scalar()
    )
    settled = -(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "platform_settle")
        .scalar()
    )
    fee_count = (
        db.query(func.count(LedgerEntry.id))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee")
        .scalar()
    )
    return {
        "balance_cents": platform.available_cents,      # 可结算余额
        "total_fee_cents": int(total_fee),              # 累计佣金收入（实收）
        "settled_cents": int(settled),                  # 已结算提走
        "fee_count": int(fee_count),
    }


def settle_platform(db: Session, amount: int, memo: str = "平台收入结算") -> dict:
    """OPS-010 平台收入结算：把平台账户余额划出（模拟对公结算/提现）。"""
    lock_wallets(db, PLATFORM_USER_ID)  # CONC-012
    platform = get_or_create(db, PLATFORM_USER_ID)
    if amount <= 0 or amount > platform.available_cents:
        raise bad_request("结算金额超出平台可用余额", "insufficient_platform_balance")
    platform.available_cents -= amount
    _log(db, PLATFORM_USER_ID, "platform_settle", -amount, memo=memo)
    return {"settled_cents": amount, "balance_cents": platform.available_cents}


def transfer(db: Session, from_id: int, to_id: int, amount: int, contract_id=None, memo="",
             kind: str = "adjust"):
    """可用余额间转账（申诉纠正性结算、GRW 补贴等平台内部调整）。

    `kind` 决定流水科目：`adjust`（默认，内部调整）/ `subsidy`（GRW 补贴）。
    补贴单独成科目的理由是对账口径不同——补贴会减少平台账户余额，
    必须计入平台账户不变量，否则日终对账会报「平台佣金不符」。
    """
    if amount <= 0:
        raise bad_request("金额必须为正", "invalid_amount")
    lock_wallets(db, from_id, to_id)  # CONC-011 按 user_id 升序加锁，避免对向转账死锁
    src = get_or_create(db, from_id)
    if src.available_cents < amount:
        raise bad_request("余额不足以执行调整", "insufficient_balance")
    src.available_cents -= amount
    _log(db, from_id, f"{kind}_out", -amount, contract_id, memo)
    dst = get_or_create(db, to_id)
    dst.available_cents += amount
    _log(db, to_id, f"{kind}_in", amount, contract_id, memo)


def fund_platform(db: Session, amount: int, memo: str = "平台补贴金注资") -> dict:
    """GRW-003 平台补贴池注资：从平台外部注入资金到平台账户。

    冷启动时平台还没有佣金收入，补贴池必须先注资才能发券——
    这笔钱同样进账本（`platform_topup`），因此全局守恒与平台账户不变量
    都能继续成立，补贴永远能追到出资方。
    """
    if amount <= 0:
        raise bad_request("注资金额必须为正", "invalid_amount")
    lock_wallets(db, PLATFORM_USER_ID)
    platform = get_or_create(db, PLATFORM_USER_ID)
    platform.available_cents += amount
    _log(db, PLATFORM_USER_ID, "platform_topup", amount, memo=memo)
    return {"balance_cents": platform.available_cents, "funded_cents": amount}


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
