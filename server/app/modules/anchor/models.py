from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class AnchorEntry(Base):
    """SC-011 存证哈希链（雏形）：append-only，每条以 prev_chain_hash 链接。

    chain_hash = sha256(prev_chain_hash + payload_hash)，任何历史记录被篡改
    都会导致后续链哈希校验失败。阶段三演进为把 chain_hash 定期锚定到公链/联盟链。
    """

    __tablename__ = "anchor_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(50))  # contract.signed / dispute.verdict ...
    ref_type: Mapped[str] = mapped_column(String(20), default="contract")
    ref_id: Mapped[int] = mapped_column(Integer, index=True)
    payload: Mapped[str] = mapped_column(Text)  # 存证内容快照（JSON 文本）
    payload_hash: Mapped[str] = mapped_column(String(64))
    prev_chain_hash: Mapped[str] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnchorReceipt(Base):
    """LAW-011 第三方存证回执：某个 seq 区间的链 head 被谁、何时背书。

    `backed=False` 表示只是平台自己记录、无外部背书——证据包必须把这个
    区别写出来（LAW-013），而不是让人误以为全都有司法效力。
    """

    __tablename__ = "anchor_receipts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq_from: Mapped[int] = mapped_column(Integer)
    seq_to: Mapped[int] = mapped_column(Integer, index=True)
    chain_head: Mapped[str] = mapped_column(String(64))
    receipt_no: Mapped[str] = mapped_column(String(120), default="")
    authority: Mapped[str] = mapped_column(String(60), default="")
    backed: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
