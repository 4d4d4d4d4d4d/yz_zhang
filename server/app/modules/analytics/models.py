from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class AnalyticsEvent(Base):
    """13.C 埋点事件（发布漏斗/接单漏斗为 P0）。轻量日志表，规模化后转数仓。"""

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(50), index=True)  # 事件名，如 task_publish_click
    ref_type: Mapped[str] = mapped_column(String(20), default="")  # task/content/...
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class SearchQuery(Base):
    """SRCH-003 搜索词记录，用于热词与联想。"""

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    term: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
