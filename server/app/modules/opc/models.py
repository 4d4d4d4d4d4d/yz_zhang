"""OPC-100 一人公司的财税与合规工具（124 号 spec）：记账底稿、申报日历、合同体检。

都是**本人私有**的数据，只出底稿与提醒：不报税、不开票、不签合同、不动钱——那些由本人在官方渠道完成。
"""
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class OpcProfile(Base):
    """主体与税务身份：决定日历上有哪些申报、汇总里按什么口径提示。"""
    __tablename__ = "opc_profiles"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # individual 个人（没有登记主体）/ sole_prop 个体工商户 / company 公司（含一人有限公司）
    entity: Mapped[str] = mapped_column(String(16), default="individual")
    # none 未登记 / small_scale 小规模纳税人 / general 一般纳税人
    vat: Mapped[str] = mapped_column(String(16), default="none")
    vat_period: Mapped[str] = mapped_column(String(8), default="quarter")     # month / quarter
    small_low_profit: Mapped[bool] = mapped_column(Boolean, default=True)     # 公司：是否小型微利企业
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OpcEntry(Base):
    """记账底稿的一行。平台收入一键导入（`source_ref` 防重复），其余手记。"""
    __tablename__ = "opc_entries"
    __table_args__ = (UniqueConstraint("owner_id", "source_ref", name="uq_opc_entry_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(8))                          # income / expense
    amount_cents: Mapped[int] = mapped_column(Integer)                    # 含税金额，正数
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)            # 发票上的税额
    category: Mapped[str] = mapped_column(String(20), default="")
    counterparty: Mapped[str] = mapped_column(String(60), default="")
    invoice_no: Mapped[str] = mapped_column(String(40), default="")
    invoice_kind: Mapped[str] = mapped_column(String(12), default="none")  # none / ordinary / special
    note: Mapped[str] = mapped_column(String(200), default="")
    source: Mapped[str] = mapped_column(String(10), default="manual")     # manual / platform
    source_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
