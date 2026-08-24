"""风控（12.D）：RISK-003 交易反欺诈 + PAY-006 对账。

反欺诈 MVP 规则：同一对手方近 7 天闭环 ≥ 3 单 → 刷单嫌疑：
- 本单不增加信用分与完成单数（防刷信用）
- 自动生成风控举报进入人审队列（RISK-002 复用）
生产演进为特征模型 + 设备指纹 + 图关系。
"""
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.events import subscribe
from app.modules.account.models import utcnow

PAIR_WINDOW_DAYS = 7
PAIR_THRESHOLD = 3  # 第 3 单起触发


def is_suspicious_pair(db: Session, creator_id: int, executor_id: int) -> bool:
    from app.modules.task.models import Task

    cutoff = utcnow() - timedelta(days=PAIR_WINDOW_DAYS)
    count = (
        db.query(Task)
        .filter(
            Task.creator_id == creator_id,
            Task.executor_id == executor_id,
            Task.status == "completed",
            Task.completed_at.isnot(None),
            Task.completed_at >= cutoff,
        )
        .count()
    )
    return count + 1 >= PAIR_THRESHOLD  # +1 计入当前正在完成的这一单


def flag_pair(db: Session, task) -> None:
    """生成风控工单进入人审队列（reporter=平台 0 号）。"""
    from app.modules.admin.models import Report

    db.add(
        Report(
            reporter_id=0,
            target_type="task",
            target_id=task.id,
            reason=(
                f"[风控自动] 用户{task.creator_id} 与 用户{task.executor_id} "
                f"近 {PAIR_WINDOW_DAYS} 天内高频互相成交，疑似刷单刷信用"
            ),
        )
    )


def reconcile(db: Session) -> dict:
    """PAY-006 对账：三条硬不变量，差错返回明细（生产为日终任务+差错工单）。

    1. 全局资金守恒：Σ(可用+托管+冻结) == Σ(用户充值 + 平台注资) - Σ(提现 + 平台结算)
    2. 托管有据：Σ escrow == Σ funded 合约的 (金额 - 已放款)
    3. 冻结有据：Σ frozen == Σ(保证金 held + 待审大额提现)
    4. 平台账户有据：平台可用 == Σ佣金 + Σ平台注资 - Σ平台结算 - Σ对外补贴净额

    第 4 条把 GRW 补贴纳入口径：补贴会减少平台余额，若不计入，
    每发一张券日终对账就会误报一次「平台佣金不符」。
    """
    from app.modules.contract.models import Contract
    from app.modules.wallet.models import LedgerEntry, WalletAccount
    from app.modules.wallet.service import PLATFORM_USER_ID

    # 进入系统的钱：用户充值 + 平台补贴池注资（GRW-003）
    total_in = db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).filter(
        LedgerEntry.kind.in_(("topup", "platform_topup"))
    ).scalar()
    # 离开系统的钱：用户提现 + 平台收入对公结算
    total_out = -db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).filter(
        LedgerEntry.kind.in_(("withdraw", "platform_settle"))
    ).scalar()
    accounts = db.query(WalletAccount).all()
    holdings = sum(a.available_cents + a.escrow_cents + a.frozen_cents for a in accounts)
    mismatches = []
    if holdings != total_in - total_out:
        mismatches.append({"invariant": "global_conservation",
                           "holdings": holdings, "expected": total_in - total_out})

    escrow_total = sum(a.escrow_cents for a in accounts)
    funded = db.query(Contract).filter(Contract.status == "funded").all()
    escrow_expected = sum(c.amount_cents - c.released_cents for c in funded)
    if escrow_total != escrow_expected:
        mismatches.append({"invariant": "escrow_backing",
                           "escrow_total": escrow_total, "expected": escrow_expected})

    frozen_total = sum(a.frozen_cents for a in accounts)
    deposit_frozen = (
        db.query(func.coalesce(func.sum(Contract.deposit_cents), 0))
        .filter(Contract.deposit_status == "held")
        .scalar()
    )
    # PAY-007：待审大额提现也占用冻结（批准划出/驳回解冻）
    from app.modules.wallet.models import WithdrawRequest

    withdraw_frozen = (
        db.query(func.coalesce(func.sum(WithdrawRequest.amount_cents), 0))
        .filter(WithdrawRequest.status == "pending")
        .scalar()
    )
    frozen_expected = int(deposit_frozen) + int(withdraw_frozen)
    if frozen_total != frozen_expected:
        mismatches.append({"invariant": "deposit_backing",
                           "frozen_total": frozen_total, "expected": frozen_expected})

    # 4. 平台佣金有据：平台账户可用余额 == 累计佣金 - 已结算
    platform = next((a for a in accounts if a.user_id == PLATFORM_USER_ID), None)
    platform_balance = platform.available_cents if platform else 0
    total_fee = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "fee")
        .scalar()
    )
    platform_settled = -(
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "platform_settle")
        .scalar()
    )
    platform_funded = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID, LedgerEntry.kind == "platform_topup")
        .scalar()
    )
    # GRW-003 补贴净额：发出去为负、退回来为正，一并计入
    platform_subsidy = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID,
                LedgerEntry.kind.in_(("subsidy_out", "subsidy_in")))
        .scalar()
    )
    # 内部调整（申诉纠正性结算）同样会动平台余额
    platform_adjust = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == PLATFORM_USER_ID,
                LedgerEntry.kind.in_(("adjust_out", "adjust_in")))
        .scalar()
    )
    platform_expected = (int(total_fee) + int(platform_funded) - int(platform_settled)
                         + int(platform_subsidy) + int(platform_adjust))
    if platform_balance != platform_expected:
        mismatches.append({"invariant": "platform_fee_backing",
                           "platform_balance": platform_balance, "expected": platform_expected})

    # FIN-060 分账守恒：任一指令的 splits 之和必须等于其总额。
    # 不守恒说明有钱凭空出现或消失，必须立刻停下来查。
    from app.modules.finance.service import verify_conservation

    for bad in verify_conservation(db):
        mismatches.append({"invariant": "settlement_conservation", **bad})

    return {"ok": not mismatches, "mismatches": mismatches,
            "accounts_checked": len(accounts), "total_holdings_cents": holdings}


def register_event_handlers() -> None:
    # 反欺诈检查挂在任务完成事件之前无法拦截（信用在 router 中处理），
    # 改由 task 完成路径显式调用 is_suspicious_pair（见 task/router._complete_task）。
    pass
