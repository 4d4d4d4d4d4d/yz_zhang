"""PWB 个人工作台（116 号 spec）：我的任务、进度、进展记录、助手记忆与例行任务。

全部是**个人私有**数据：不公开、不进搜索、不进推荐、不进经验库。
与平台任务（`tasks`）是两张表：平台任务有钱、有合约、有对方；个人任务只关乎自己。
二者通过 `linked_task_id` 关联——「我在平台上发的单 / 接的单」可以放进自己的工作台一起看进度。
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class WbProject(Base):
    __tablename__ = "wb_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60))
    color: Mapped[str] = mapped_column(String(16), default="clay")
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WbItem(Base):
    __tablename__ = "wb_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # 清单子项：只有一层（子项不能再有子项），够用且不会把个人待办做成第二个分解树
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="todo")
    priority: Mapped[int] = mapped_column(Integer, default=1)       # 0 低 / 1 普通 / 2 高 / 3 紧急
    category: Mapped[str] = mapped_column(String(40), default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    remind_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    linked_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WbLog(Base):
    __tablename__ = "wb_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(Integer, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="note")   # note / status / progress / assistant
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WbMemory(Base):
    __tablename__ = "wb_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    content: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WbRoutine(Base):
    __tablename__ = "wb_routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(16))                   # digest / review / reminder
    freq: Mapped[str] = mapped_column(String(16))                   # once / daily / weekly / monthly
    time_of_day: Mapped[str] = mapped_column(String(5), default="09:00")   # 北京时间 HH:MM
    weekday: Mapped[int] = mapped_column(Integer, default=0)        # 0=周一
    monthday: Mapped[int] = mapped_column(Integer, default=1)
    run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # once：UTC
    note: Mapped[str] = mapped_column(String(500), default="")
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str] = mapped_column(String(16), default="")
    failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # REL-101 运行合同（130 号 spec）：超时、失败重试几次、重试用尽时是否降级交付。默认不重试、不降级（与 V141 行为一致）
    timeout_ms: Mapped[int] = mapped_column(Integer, default=10000)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    degrade: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)                 # 当前这次排期已经重试了几次
    pending_slot_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)   # 正在重试的是哪一次排期


class WbRoutineRun(Base):
    __tablename__ = "wb_routine_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    routine_id: Mapped[int] = mapped_column(Integer, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(16))
    output: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # REL-105 运行日志：哪次排期、第几次尝试、耗时、成本、错误类型（只记类型，不记异常文本——可能带个人内容）
    slot_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    error_kind: Mapped[str] = mapped_column(String(40), default="")
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
