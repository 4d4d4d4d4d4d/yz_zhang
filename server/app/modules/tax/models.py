"""TAX-020 代扣记录：完税凭证的数据来源，也是执行者汇算清缴要拿的东西。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class TaxWithholding(Base):
    """一次支付一条。只增不改——税务记录被事后修改就失去了全部意义。"""

    __tablename__ = "tax_withholdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)       # 纳税人
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    settlement_kind: Mapped[str] = mapped_column(String(24), default="release")
    # 归属执行者的含税收入（已扣平台佣金后的净额，见 TAX-004 的口径说明）
    income_cents: Mapped[int] = mapped_column(Integer, default=0)
    taxable_cents: Mapped[int] = mapped_column(Integer, default=0)
    withheld_cents: Mapped[int] = mapped_column(Integer, default=0)
    # 适用规则与说明：口径调整时要能说清历史每一笔是按什么算的
    rule: Mapped[str] = mapped_column(String(32), default="none")
    mode: Mapped[str] = mapped_column(String(16), default="none")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class InvoiceRequest(Base):
    """TAX-022/023 开票请求。

    两种：平台服务费发票（平台可开）、执行者报酬发票（平台**无权**开，
    须由执行者或代开渠道提供）。把它们放在同一张表里、用 kind 区分，
    是为了让「谁该给谁开票」这件事在数据上一目了然。
    """

    __tablename__ = "invoice_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # platform_fee = 平台服务费（平台开给发布方）
    # executor_fee = 执行者报酬（执行者开给平台/发布方，平台只登记义务）
    kind: Mapped[str] = mapped_column(String(16), index=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)   # 申请人
    contract_id: Mapped[int] = mapped_column(Integer, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(120), default="")      # 抬头
    tax_no: Mapped[str] = mapped_column(String(40), default="")      # 纳税人识别号
    # pending / issued / rejected
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
