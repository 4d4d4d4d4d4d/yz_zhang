"""ACC-003 第三方身份绑定。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    # 一个第三方账号只能绑一个本站账号，否则「用微信登录」会不确定登进哪个
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), index=True)  # wechat/apple/google
    # **subject 是第三方给的稳定标识，不是邮箱也不是手机号**——
    # 邮箱会变，Apple 还允许用户隐藏真实邮箱；拿它当主键迟早认错人
    subject: Mapped[str] = mapped_column(String(191), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
