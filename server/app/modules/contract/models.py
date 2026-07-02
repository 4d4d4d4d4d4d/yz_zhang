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
    fee_bps: Mapped[int] = mapped_column(Integer)  # SC-009 平台佣金（万分比）
    terms: Mapped[str] = mapped_column(Text, default="")  # SC-001 条款文本（由任务要素生成）
    status: Mapped[str] = mapped_column(String(30), default="pending_signatures")
    signed_by_requester: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_by_executor: Mapped[bool] = mapped_column(Boolean, default=False)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # SC-008 纠纷冻结
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    funded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
