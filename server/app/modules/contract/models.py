from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# SC 合约生命周期：pending_signatures → signed → funded → released/refunded/split/cancelled
CONTRACT_STATUSES = [
    "pending_signatures",
    "signed",
    "funded",
    "released",
    "refunded",
    "split",
    "cancelled",
]


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    executor_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    released_cents: Mapped[int] = mapped_column(Integer, default=0)  # SC-004 已分期放款累计
    fee_bps: Mapped[int] = mapped_column(Integer)  # SC-009 平台佣金（万分比）
    terms: Mapped[str] = mapped_column(Text, default="")  # SC-001 条款文本（由任务要素生成）
    status: Mapped[str] = mapped_column(String(30), default="pending_signatures")
    signed_by_requester: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_by_executor: Mapped[bool] = mapped_column(Boolean, default=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # SC-008 纠纷冻结
    version: Mapped[int] = mapped_column(Integer, default=1)  # SC-007 变更单生效则 +1
    # CONC-013 乐观锁：与业务版本号 version 分离（后者是合约条款版本，会被展示与导出）。
    # 每次 ORM UPDATE 自动 +1 并进入 WHERE 条件，并发写第二个提交拿到 StaleDataError → 409
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # CRED-005 执行者保证金
    deposit_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_status: Mapped[str] = mapped_column(String(12), default="none")  # none/held/returned/forfeited
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __mapper_args__ = {"version_id_col": lock_version}


class Milestone(Base):
    """SC-004 里程碑分期：每期独立交付/验收/放款。默认单期=全额。"""

    __tablename__ = "milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    idx: Mapped[int] = mapped_column(Integer)  # 1..n
    title: Mapped[str] = mapped_column(String(120), default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/delivered/released
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChangeOrder(Base):
    """SC-007 变更单：改价需对方接受，生效后合约版本 +1、托管差额多退少补。"""

    __tablename__ = "change_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    proposed_by: Mapped[int] = mapped_column(Integer)
    new_amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
