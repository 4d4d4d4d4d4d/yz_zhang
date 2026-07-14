from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200), default="")
    nickname: Mapped[str] = mapped_column(String(50), default="")
    bio: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(50), default="", index=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    # ACC-011 技能标签 / ACC-015 兴趣标签
    skills: Mapped[list] = mapped_column(JSON, default=list)
    interests: Mapped[list] = mapped_column(JSON, default=list)
    # ACC-022 职业资质（如 律师/电工），受限类目接单准入
    certifications: Mapped[list] = mapped_column(JSON, default=list)
    # ACC-030 隐私设置：profile_public=False 时公开名片仅显示昵称与信用
    privacy: Mapped[dict] = mapped_column(JSON, default=dict)
    # ACC-013 服务定价（分/次，0=面议）与可接单时间描述
    service_rate_cents: Mapped[int] = mapped_column(Integer, default=0)
    available_times: Mapped[str] = mapped_column(String(200), default="")
    # ACC-014 接单开关（业界「上线/下线」）：关闭后不进推荐、不可被邀约；主动报名不受限
    accepting_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    # ACC-020 实名认证（模拟 eKYC 通过后置位；接单/提现前强制）
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    real_name: Mapped[str] = mapped_column(String(50), default="")
    # 平台侧角色（OPS-001 简化：仲裁/运营用）
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # RISK-006 封禁（封禁后所有需登录操作被拒）
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    # ACC-006 注销（脱敏保留，登录与被检索均拒绝）
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    # CNT-022 邀请裂变：本人邀请码 + 邀请人 id + 首单奖励是否已发放
    referral_code: Mapped[str] = mapped_column(String(12), default="", index=True)
    referred_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    referral_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    # CRED-001 信用分（初始 100）与评价聚合
    credit_score: Mapped[int] = mapped_column(Integer, default=100)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    @property
    def rating_avg(self) -> float:
        return round(self.rating_sum / self.rating_count, 2) if self.rating_count else 0.0


class LoginSession(Base):
    """ACC-005 登录会话：设备管理与踢出。"""

    __tablename__ = "login_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    device: Mapped[str] = mapped_column(String(200), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Block(Base):
    """ACC-033 黑名单：拉黑后不再互相匹配/私聊/报名。"""

    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(Integer, index=True)
    blocked_id: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
