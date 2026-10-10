"""幂等键支持（14.6「所有写操作支持 Idempotency-Key，资金类强制」/ 05.B 资金幂等）。

同一 (user, key) 的资金操作重复提交时直接返回首次结果，避免网络重试导致重复扣款。
参照 Stripe：记录请求指纹（scope + 参数哈希）；同 key 但参数/操作不同 → 冲突拒绝，
杜绝「复用旧 key 提交新金额被静默吞掉」与「同 key 跨操作串味」两类隐患。
"""
import hashlib
import json

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base
from app.core.errors import conflict
from app.modules.account.models import utcnow


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    key: Mapped[str] = mapped_column(String(80), index=True)
    scope: Mapped[str] = mapped_column(String(40))  # 操作类型，如 wallet.topup
    fingerprint: Mapped[str] = mapped_column(String(64), default="")  # scope + 参数指纹
    response: Mapped[str] = mapped_column(Text)  # 首次结果 JSON
    created_at: Mapped[DateTime] = mapped_column(DateTime, default=utcnow)


def _fingerprint(scope: str, params: dict | None) -> str:
    payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{scope}|{payload}".encode()).hexdigest()


def replay_or_run(db: Session, user_id: int, key: str | None, scope: str, run,
                  params: dict | None = None):
    """key 为空则直接执行；否则命中缓存且指纹一致返回旧结果，未命中执行并记录。

    同 key 但 (scope, params) 指纹不同 → 409 idempotency_key_conflict（防串味/防吞单）。
    run() 必须返回可 JSON 序列化的 dict。
    """
    if not key:
        return run()
    fp = _fingerprint(scope, params)
    existing = (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
        .first()
    )
    if existing:
        if existing.fingerprint and existing.fingerprint != fp:
            raise conflict(
                "幂等键已用于不同的请求，请更换 Idempotency-Key", "idempotency_key_conflict"
            )
        return json.loads(existing.response)
    result = run()
    db.add(
        IdempotencyRecord(
            user_id=user_id, key=key[:80], scope=scope, fingerprint=fp,
            response=json.dumps(result, ensure_ascii=False),
        )
    )
    db.flush()
    return result
