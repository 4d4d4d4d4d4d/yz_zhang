from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class WalletAccount(Base):
    """SC-020 三态账本：可用 / 托管中(我付出的) / 冻结中(纠纷)。金额一律整数分。"""

    __tablename__ = "wallet_accounts"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    available_cents: Mapped[int] = mapped_column(Integer, default=0)
    escrow_cents: Mapped[int] = mapped_column(Integer, default=0)
    frozen_cents: Mapped[int] = mapped_column(Integer, default=0)
    # CONC-013 乐观锁：并发扣款只有一个提交能成功，另一个 409 而不是丢更新
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": lock_version}


class LedgerEntry(Base):
    """SC-022 流水：只增不改，每笔可追溯到合约。"""

    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    # topup 充值 / withdraw 提现 / escrow_hold 托管冻结 / escrow_release 托管放款收入
    # refund 退款 / fee 平台佣金 / dispute_split 纠纷分割
    kind: Mapped[str] = mapped_column(String(30))
    amount_cents: Mapped[int] = mapped_column(Integer)  # 正=入账 负=出账（对 available）
    contract_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    memo: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FinancePeriodLock(Base):
    """FIN-063（223 号 spec）已锁账的月份：锁账那一刻的报表快照。之后这个月的报表只读快照，
    锁账后才记进来的流水（「补记」）记到锁账之后的第一个未锁月份，不改已出的数。"""

    __tablename__ = "finance_period_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True)          # 北京时间自然月 2026-09
    snapshot: Mapped[dict] = mapped_column(JSON)                         # 锁账时这个月的报表行
    in_month_cents: Mapped[int] = mapped_column(Integer, default=0)      # 锁账时记在这个月里的流水合计与笔数
    in_month_count: Mapped[int] = mapped_column(Integer, default=0)
    cumulative: Mapped[dict] = mapped_column(JSON)                       # 锁账时月末以前的累计（按报表栏目，含笔数）
    locked_by: Mapped[int] = mapped_column(Integer)
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WithdrawRequest(Base):
    """PAY-007 大额提现人审：申请即冻结，批准划出/驳回解冻（业界 T+人审惯例）。"""

    __tablename__ = "withdraw_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    # pending / awaiting_second（大额已一审、等第二人确认）/ sending（已提交银行、等结果，CONC-067）/
    # approved（人审放款）/ paid（即时提现到账）/ failed（即时提现银行明确拒绝，已解冻）/ rejected
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PAY-042 四眼原则：大额出款的第一次批准记在这里，**钱不动**；
    # 第二个管理员确认后才放款。两次必须是不同的人——
    # 否则就是同一个人点两次，等于没有这条规则。
    first_approved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # PAY-044 上一次催办管理员的时间（75 号 spec）。
    # 没有它，一审通过的申请会永远停在 awaiting_second——
    # 加一道控制的同时加了一个新的卡点，而卡点没有兜底就是新的「钱能进不能出」。
    review_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PayoutAccount(Base):
    """PAY-005 收款账户绑定：提现前置（业界必备，模拟银行卡/支付宝绑定）。"""

    __tablename__ = "payout_accounts"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 一人一账户（MVP）
    kind: Mapped[str] = mapped_column(String(12), default="bank")  # bank/alipay
    account_no: Mapped[str] = mapped_column(String(64))
    holder_name: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
