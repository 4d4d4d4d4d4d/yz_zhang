from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# 03.A 任务状态机
TASK_STATUSES = [
    "draft",  # 草稿
    "published",  # 已发布(招募中)
    "matched",  # 已匹配(合约签署/托管中)
    "in_progress",  # 执行中
    "pending_acceptance",  # 待验收
    "completed",  # 已完成
    "cancelled",  # 已取消
    "disputed",  # 纠纷中
]

# 状态流转白名单（TASK 状态机 P0：非法流转一律拒绝）
TRANSITIONS: dict[str, set[str]] = {
    "draft": {"published", "cancelled"},
    "published": {"matched", "cancelled"},
    "matched": {"in_progress", "cancelled", "disputed"},
    "in_progress": {"pending_acceptance", "cancelled", "disputed"},
    "pending_acceptance": {"completed", "in_progress", "disputed"},
    "disputed": {"completed", "cancelled", "in_progress"},
    "completed": set(),
    "cancelled": set(),
}

TASK_TYPES = ["service", "trade", "project", "event"]  # 服务/交易/项目/事件


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creator_id: Mapped[int] = mapped_column(Integer, index=True)
    executor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 04 子任务树：parent_id + depends_on(兄弟任务 id 列表, DAG)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    depends_on: Mapped[list] = mapped_column(JSON, default=list)

    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), index=True)  # 类目：保洁/跑腿/开发...
    task_type: Mapped[str] = mapped_column(String(20), default="service")
    required_skills: Mapped[list] = mapped_column(JSON, default=list)

    budget_cents: Mapped[int] = mapped_column(Integer, default=0)
    pricing: Mapped[str] = mapped_column(String(20), default="fixed")  # fixed 一口价 / bidding 竞价

    # GEO：is_remote 线上任务不限地域；线下任务坐标 + 脱敏地址(公开) + 精确地址(成交后可见)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str] = mapped_column(String(50), default="", index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    address_hint: Mapped[str] = mapped_column(String(120), default="")  # 商圈级(GEO-004)
    address_exact: Mapped[str] = mapped_column(String(200), default="")

    # TASK-008 可见范围：public 公开广场 / circle 仅圈层任务板
    visibility: Mapped[str] = mapped_column(String(12), default="public")
    circle_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # TASK-006 周期任务：none/weekly/monthly，闭环后自动生成下一期
    recurrence: Mapped[str] = mapped_column(String(10), default="none")
    recurred_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_count: Mapped[int] = mapped_column(Integer, default=0)  # 验收驳回次数(TASK-033)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Application(Base):
    """MATCH-001 报名/报价。"""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    applicant_id: Mapped[int] = mapped_column(Integer, index=True)
    bid_cents: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/accepted/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProgressLog(Base):
    """TASK-022 进度留痕 + GEO-020 打卡（作为履约与纠纷证据）。"""

    __tablename__ = "progress_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note/checkin/delivery
    content: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Review(Base):
    """TASK-034/CRED-002 双向盲评：双方都提交或超时后才互相可见。"""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    reviewer_id: Mapped[int] = mapped_column(Integer)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    stars: Mapped[int] = mapped_column(Integer)  # 1..5
    tags: Mapped[list] = mapped_column(JSON, default=list)
    comment: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
