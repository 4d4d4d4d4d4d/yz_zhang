"""PACK-100 场景包与平台资产（123 号 spec）。

一个**场景包**把服务某类人的某个痛点所需的平台资产打成一包：
助手专家（人设 + 方法 + 工具白名单 + 人工关口）、方法（步骤清单）、知识条目（有出处、有有效期）、
例行任务模板、任务模板。场景包是**数据**：定义 → 校验 → 审核（四眼）→ 上线 → 用户一键启用 → 指标 → 复核或下线。
新场景不靠写新页面上线，而是靠写一个新的包（VISION 1.8）。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class ScenarioPack(Base):
    __tablename__ = "scenario_packs"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_scenario_pack_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(80))
    segment: Mapped[str] = mapped_column(String(30))
    summary: Mapped[str] = mapped_column(String(500), default="")
    # draft → review → published →（新版本上线后）superseded；任何时候可 retired（写理由，只增不删）
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    definition: Mapped[dict] = mapped_column(JSON, default=dict)     # 校验过的完整定义（含资产）
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_by: Mapped[int] = mapped_column(Integer)
    reviewed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    retired_reason: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # SCN-163（292 号 spec）上次提醒「知识快到期了」的时间：同一个包一周最多提醒一次
    expiry_reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PackEnrollment(Base):
    """用户启用了哪个包的哪个版本，装进了自己哪些东西（方法 / 笔记 / 例行任务的 id）。"""
    __tablename__ = "pack_enrollments"
    __table_args__ = (UniqueConstraint("user_id", "pack_key", name="uq_pack_enrollment_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    pack_key: Mapped[str] = mapped_column(String(60), index=True)
    pack_id: Mapped[int] = mapped_column(Integer, index=True)       # 启用（或最近一次升级）时的那个版本
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")   # active / removed
    installed: Mapped[dict] = mapped_column(JSON, default=dict)     # {"methods": [...], "notes": [...], "routines": [...]}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PackEvent(Base):
    """效果指标的原始事件。只记**发生了什么**，不记内容（提问原文不落库）。"""
    __tablename__ = "pack_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_key: Mapped[str] = mapped_column(String(60), index=True)
    pack_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16))      # enable / disable / ask / unanswered / refused / helpful / unhelpful
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
