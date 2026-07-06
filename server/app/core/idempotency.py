"""幂等键支持（14.6「所有写操作支持 Idempotency-Key，资金类强制」/ 05.B 资金幂等）。

同一 (user, key) 的资金操作重复提交时直接返回首次结果，避免网络重试导致重复扣款。
"""
import json

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.modules.account.models import utcnow


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    scope: Mapped[str] = mapped_column(String(40))  # 操作类型，如 wallet.topup
    response: Mapped[str] = mapped_column(Text)  # 首次结果 JSON
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=utcnow)


def replay_or_run(db: Session, user_id: int, key: str | None, scope: str, run):
    """key 为空则直接执行；否则命中缓存返回旧结果，未命中执行并记录。

    run() 必须返回可 JSON 序列化的 dict。
    """
    if not key:
        return run()
    existing = (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
        .first()
    )
    if existing:
        return json.loads(existing.response)
    result = run()
    db.add(
        IdempotencyRecord(
            user_id=user_id, key=key[:80], scope=scope,
            response=json.dumps(result, ensure_ascii=False),
        )
    )
    db.flush()
    return result
