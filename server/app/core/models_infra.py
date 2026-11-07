"""基础设施表（非业务域）：定时任务执行锁等。"""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class JobLock(Base):
    """CONC-041 定时任务单实例锁。

    job_name 作主键即天然唯一约束：多副本同时抢占，DB 保证只有一个成功。
    `expires_at` 到期可被抢占——持锁进程崩溃不会让 job 永久停摆。
    """

    __tablename__ = "job_locks"

    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64), default="")
    locked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # DEP-051 job 健康：上次成功完成时间。超过预期周期 2 倍未成功即告警——
    # 定时任务「静默不跑」比报错更危险（自动验收停摆 = 资金永久卡在托管）
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(200), default="")
