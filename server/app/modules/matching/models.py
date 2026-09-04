from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Invitation(Base):
    """MATCH-004 定向邀约。"""

    __tablename__ = "invitations"
    __table_args__ = (UniqueConstraint("task_id", "invitee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    inviter_id: Mapped[int] = mapped_column(Integer)
    invitee_id: Mapped[int] = mapped_column(Integer, index=True)
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/declined
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MatchingConfig(Base):
    """MATCH-008 匹配策略配置（后台调参，实时生效）。"""

    __tablename__ = "matching_configs"

    key: Mapped[str] = mapped_column(String(30), primary_key=True)  # "weights"
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Subscription(Base):
    """TASK-042 任务订阅：类目+城市，新任务发布即通知。"""

    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "category", "city"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(50))
    city: Mapped[str] = mapped_column(String(50), default="")  # 空 = 不限城市
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
