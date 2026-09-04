from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Report(Base):
    """RISK-007 举报中心：全对象可举报，进入人审队列（RISK-002）。"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(Integer, index=True)
    target_type: Mapped[str] = mapped_column(String(20))  # task/content/user/message
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/resolved
    action: Mapped[str] = mapped_column(String(20), default="")  # dismiss/remove_content/ban_user
    handled_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AdminAudit(Base):
    """OPS-012 管理员操作审计：高权限动作（封禁/裁决/结算等）不可抵赖留痕。

    只增不改，记录 谁(admin_id) 在何时 对什么对象(target) 做了什么(action)。
    """

    __tablename__ = "admin_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)  # ban_user/dispute_verdict/...
    target_type: Mapped[str] = mapped_column(String(20), default="")
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
