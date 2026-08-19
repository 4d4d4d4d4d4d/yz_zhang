from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Dispute(Base):
    """DSP-001 纠纷：协商 → 平台仲裁 → 裁决自动执行。"""

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    opened_by: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open/resolved/settled
    # DSP-003 证据链自动归集快照
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    # 和解提案（DSP-004）：{"executor_share_bps": int, "proposed_by": user_id}
    settlement_proposal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 裁决（DSP-006/007）
    verdict_executor_share_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict_reason: Mapped[str] = mapped_column(Text, default="")
    arbiter_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # DSP-008 申诉复核（一次）：记录裁决执行时的分割基数用于纠正性结算
    split_base_cents: Mapped[int] = mapped_column(Integer, default=0)
    appealed: Mapped[bool] = mapped_column(Boolean, default=False)
    # DSP-009 SLA 升级标记：超期未结案已进人审队列（幂等去重）
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DisputeStatement(Base):
    """DSP-005 答辩/举证陈述：两造兼听的载体，只增不改（证据链要求）。"""

    __tablename__ = "dispute_statements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispute_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(12))  # opener 发起方 / respondent 被诉方
    content: Mapped[str] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSON, default=list)  # 图片/文件 URL
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
