"""FIN-010 分账指令（25 号 spec）。

合规形态下，钱**不经过平台**：用户资金在持牌机构的存管账户里，
平台只发「分账指令」（谁收、收多少、什么事由），由存管方执行。

因此这两张表是资金流的**事实记录**：
- 接存管前：它是平台内账本的镜像（FIN-002），用于校验与对账；
- 接存管后：它就是发给存管方的指令本身，`custody_ref` 记录对方流水号。

无论哪种形态，**splits 之和必须等于 total**——这是分账不丢钱的硬约束。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 指令类型：验收放款 / 分期放款 / 取消退款 / 纠纷分割 / 裁决执行
SETTLEMENT_KINDS = ("release", "milestone", "refund", "split", "verdict")
# 收款用途：执行者报酬 / 平台服务费 / 退还发布方 / 违约补偿 / 代扣税费
SPLIT_PURPOSES = ("payout", "fee", "refund", "compensation", "tax")


class SettlementOrder(Base):
    """一次资金分配指令。"""

    __tablename__ = "settlement_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))
    total_cents: Mapped[int] = mapped_column(Integer)
    # internal（平台内账本，仅限开发/演示）/ custody（持牌机构存管）
    backend: Mapped[str] = mapped_column(String(16), default="internal")
    status: Mapped[str] = mapped_column(String(16), default="executed")
    # FIN-004 存管方流水号：无流水号的账目视为异常并告警（接存管后必填）
    custody_ref: Mapped[str] = mapped_column(String(80), default="")
    memo: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SettlementSplit(Base):
    """指令中的一个收款方。金额之和必须等于订单总额（整数分，不允许尾差蒸发）。"""

    __tablename__ = "settlement_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(Integer, index=True)
    payee_user_id: Mapped[int] = mapped_column(Integer, index=True)  # 0 = 平台账户
    amount_cents: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(16), default="payout")
