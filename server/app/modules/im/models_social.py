"""IM-020/021 好友关系。

原始 spec 写得很明确：「**双向同意**」。这一条不是礼貌，是反骚扰的地基——
单向加好友等于给任何人开了一条无需对方许可的私聊通道，
而这个平台上陌生人之间本来就有真金白银的往来。
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class Friendship(Base):
    __tablename__ = "friendships"
    # 一对人只能有一条记录：否则双方同时发起会攒出两条，
    # 「接受」哪一条都对，而另一条永远悬着
    __table_args__ = (UniqueConstraint("requester_id", "addressee_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(Integer, index=True)
    addressee_id: Mapped[int] = mapped_column(Integer, index=True)
    # pending 待对方同意 / accepted 已成为好友 / rejected 已拒绝
    status: Mapped[str] = mapped_column(String(10), default="pending")
    # IM-021 备注名是**各自看各自的**，所以存在关系行上按方向取
    requester_remark: Mapped[str] = mapped_column(String(50), default="")
    addressee_remark: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
