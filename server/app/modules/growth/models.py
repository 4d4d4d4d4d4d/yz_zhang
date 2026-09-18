"""增长与运营（22 号 spec / GRW）：优惠券、活动、邀请奖励。

**资金口径贯穿全模块**：补贴不凭空产生，一律由平台账户出资并走既有账本，
资金四不变量（全局守恒 / 托管有据 / 冻结有据 / 平台账户有据）必须恒成立。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow

# GRW-001 券类型：发布方立减（成交时平台补给发布方）/ 接单方补贴（完成时平台补给执行方）
COUPON_KINDS = ("requester_discount", "worker_bonus")


class Campaign(Base):
    """GRW-030 活动：给一组券套上时间窗、定向与**预算硬顶**。

    没有预算硬顶的补贴活动是运营事故的标准形态——本表的 `spent_cents`
    在每次核销时同步累加，超顶即停投，不依赖人盯。
    """

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(50), default="")       # 空=不限
    category: Mapped[str] = mapped_column(String(50), default="")   # 空=不限
    budget_cap_cents: Mapped[int] = mapped_column(Integer)
    spent_cents: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Coupon(Base):
    """GRW-001 券模板。面额与比例二选一（比例券必须有封顶，否则大额单会失控）。"""

    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(24), default="requester_discount")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)   # 定额券
    percent_bps: Mapped[int] = mapped_column(Integer, default=0)    # 比例券（万分比）
    max_discount_cents: Mapped[int] = mapped_column(Integer, default=0)  # 比例券封顶
    min_order_cents: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(50), default="")   # 空=不限类目
    newcomer_only: Mapped[bool] = mapped_column(Boolean, default=False)
    total_quota: Mapped[int] = mapped_column(Integer, default=0)    # 0=不限量
    issued_count: Mapped[int] = mapped_column(Integer, default=0)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1)
    valid_days: Mapped[int] = mapped_column(Integer, default=30)    # 领取后有效期
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UserCoupon(Base):
    """GRW-002 用户持有的券。核销与合约绑定，一单只能用一张。"""

    __tablename__ = "user_coupons"
    __table_args__ = (
        # 同一合约只允许一次核销记录，DB 层兜住「一单一券」
        UniqueConstraint("contract_id", name="uq_user_coupon_contract"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coupon_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(12), default="unused")  # unused/used/expired
    contract_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)    # 实际核销金额
    claimed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReferralReward(Base):
    """GRW-012/013 邀请奖励：**被邀请人完成首单且过评价期**才发，不是注册即发。

    `status=blocked` 用于反作弊命中（同设备/同收款账户成环），
    进人工复核而非直接发钱。
    """

    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("invitee_id", name="uq_referral_invitee"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inviter_id: Mapped[int] = mapped_column(Integer, index=True)
    invitee_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="granted")  # granted/blocked
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
