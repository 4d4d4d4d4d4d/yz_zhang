from datetime import datetime

from sqlalchemy import DateTime, Integer, String
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


class WithdrawRequest(Base):
    """PAY-007 大额提现人审：申请即冻结，批准划出/驳回解冻（业界 T+人审惯例）。"""

    __tablename__ = "withdraw_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending/approved/rejected
    decided_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
