from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
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
