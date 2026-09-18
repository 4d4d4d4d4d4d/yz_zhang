"""NTF-002 设备令牌：推送的收件地址。

没有这张表，推送通道接了也无处可发——这是「推送通道」这件事里
最容易被忽略、却是第一步的那一半。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    # 令牌本身就是主键：同一个设备重复注册应当是幂等的，
    # 而不是攒出一堆重复行然后推四遍
    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    platform: Mapped[str] = mapped_column(String(10), default="ios")  # ios/android/web
    # 设备卸载后令牌永久失效；不清理就会年复一年地推给不存在的设备，
    # 而通道按量计费。供应商回报失效即置位。
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
