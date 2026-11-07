"""INF-100 影响力与专家等级（127 号 spec）：只能靠闭环合作挣、不可转让、可质押担保、败诉罚没、按时间衰减、快照锚定。

影响力**不是钱**：不能充值、不能提现、不能转给别人（没有任何转让接口，闸门钉住）。
它是一本只增不改的账：挣、罚、恢复都是一条事件；「现在有多少」按半衰期在读的时候算。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class InfluenceEvent(Base):
    __tablename__ = "influence_events"
    # 同一件事只记一次：同一单的收入、同一次纠纷的罚没，重放事件不会重复记
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref_type", "ref_id", name="uq_influence_event_once"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    # earn_task 完成一单 / earn_publish 发单方的闭环 / earn_vouch 担保的人做成了 /
    # slash_dispute 纠纷败诉 / slash_vouch 担保的人败诉 / restore 申诉改判后恢复
    kind: Mapped[str] = mapped_column(String(20))
    points: Mapped[float] = mapped_column(Float)
    ref_type: Mapped[str] = mapped_column(String(20))
    ref_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class InfluenceVouch(Base):
    """质押担保：熟手以上拿自己在这个类目的影响力为别人作保。对方做成了，担保人得一点；对方败诉，罚没一半。"""
    __tablename__ = "influence_vouches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voucher_id: Mapped[int] = mapped_column(Integer, index=True)
    subject_id: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(50))
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)   # 为某一单作保；空 = 整个类目
    stake: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)    # active / released / slashed / withdrawn
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispute_id: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 被哪一次纠纷罚没：申诉改判时据此恢复


class InfluenceSnapshot(Base):
    """每日快照：所有人各类目的影响力做成 Merkle 树，根锚定进存证哈希链（anchor_entries）。"""
    __tablename__ = "influence_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    taken_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    merkle_root: Mapped[str] = mapped_column(String(64))
    leaves: Mapped[int] = mapped_column(Integer, default=0)
    anchor_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entries: Mapped[list] = mapped_column(JSON, default=list)      # [[user_id, 类目, 影响力], …]：证明用，不对外
