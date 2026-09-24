"""SECEV-001 安全事件表（31 号 spec）。

放在 `core` 而不是某个业务模块下：`guard.py` 是所有请求都会过的边界层，
让它依赖某个业务模块会把依赖方向拧反。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

KINDS = (
    "auth_failure",       # 认证失败（高频，保留期到了会被清理）
    "ban",                # 自动封禁（运营处置留痕，不随保留期清理）
    "unban",              # 人工解封（同上）
    "captcha_required",   # 触发软阈值，要求人机验证
    "captcha_failed",     # 人机验证未通过
    "captcha_passed",     # 人机验证通过
)


class SecurityEvent(Base):
    """一条安全事件。

    **封禁状态以本表为准**，不再是进程内的 dict——多副本下进程内状态
    等于「每个副本各封各的、各解各的」，被误封的用户会遇到时好时坏的故障，
    那比稳定的故障难查一个数量级。
    """

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    ip: Mapped[str] = mapped_column(String(64), index=True)
    # 相关账号（认证失败时往往还不知道是谁，允许为空）
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="")   # login/register/...
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # 仅 ban 使用：封禁到期时间。解封 = 把它改成「现在」，而不是删记录
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
