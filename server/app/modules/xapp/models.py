"""XAPP 跨 App 助手（161 号 spec）：授权、一次执行、执行的每一步。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class XappGrant(Base):
    """XAPP-001 用户给自己的设备开的操作授权：哪些 App、哪些动作、到期时间、要不要让云端模型看屏幕。"""
    __tablename__ = "xapp_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    device_label: Mapped[str] = mapped_column(String(60), default="")
    apps: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    allow_cloud_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class XappRun(Base):
    """XAPP-002 一次执行：目标、计划、确认方式、执行器类型、状态。"""
    __tablename__ = "xapp_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    grant_id: Mapped[int] = mapped_column(Integer, index=True)
    goal: Mapped[str] = mapped_column(String(200))
    executor: Mapped[str] = mapped_column(String(16), default="mock")
    confirm_mode: Mapped[str] = mapped_column(String(12), default="red_only")   # each / red_only
    # running / needs_human / stopped / done / failed
    status: Mapped[str] = mapped_column(String(12), default="running", index=True)
    stop_reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class XappStep(Base):
    """XAPP-002/003 每一步：在哪个 App、做什么、用哪个通道；红线步由本人亲手做。
    结果只存脱敏后的文字摘要，截图原图不出设备（XAPP-005）。"""
    __tablename__ = "xapp_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    app: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(20))
    intent: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(10))
    vision_where: Mapped[str] = mapped_column(String(8), default="device")
    red_line: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # pending / dispatched / done / done_by_user / failed / skipped
    status: Mapped[str] = mapped_column(String(14), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
