from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Notification(Base):
    """NTF-001 站内信，事件驱动生成（NTF-004）。"""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(20), default="system")  # task/funds/system
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(500), default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # NTF-064 来自哪条全站公告（151 号 spec）：撤回时据此把已送达的通知标成「已撤回」
    announcement_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # NTF-072（261 号 spec）第一次点开的时间：公告阅读率按发出后的时间看；这一版之前读过的为空
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # NTF-073（268 号 spec）第一次是从哪里点开的：push 推送 / center 通知中心；空 = 没说（老客户端与这一版之前）
    read_via: Mapped[str] = mapped_column(String(8), default="")
