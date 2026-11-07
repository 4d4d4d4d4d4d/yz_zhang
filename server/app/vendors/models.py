"""VND-003/011 外部调用留痕与支付订单。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class VendorCall(Base):
    """VND-003 外部调用流水：对账与客诉排查的唯一依据。

    只存脱敏摘要与外部单号——排查够用，泄露风险最小。
    """

    __tablename__ = "vendor_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)  # payment/sms/kyc/moderation/storage
    provider: Mapped[str] = mapped_column(String(30))
    operation: Mapped[str] = mapped_column(String(40))
    idem_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    request_digest: Mapped[str] = mapped_column(String(400), default="")
    status: Mapped[str] = mapped_column(String(16), default="succeeded")  # succeeded/failed/pending
    external_ref: Mapped[str] = mapped_column(String(80), default="")
    error_code: Mapped[str] = mapped_column(String(40), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PaymentOrder(Base):
    """VND-011 充值两阶段：下单 pending → 供应商确认 succeeded 才入账。

    此前「调用即加余额」在真实支付下是致命的——用户可以下单不付款却拿到余额。
    Mock 供应商即时确认，因此对开发/测试体验无影响，但结构已是生产形态。
    """

    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    # pending 待支付 / succeeded 已入账 / failed 失败 / mismatch 金额不符（挂起人工）
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    external_ref: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SmsCode(Base):
    """VND-021 验证码：**只存哈希**（手机号加盐），带有效期与尝试次数上限。

    泄库也无法直接冒用；尝试次数上限挡住 6 位码的暴力枚举。
    """

    __tablename__ = "sms_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    scene: Mapped[str] = mapped_column(String(20), default="verify")
    code_hash: Mapped[str] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
