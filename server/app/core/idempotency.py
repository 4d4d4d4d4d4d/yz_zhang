"""幂等键支持（14.6「所有写操作支持 Idempotency-Key，资金类强制」/ 05.B 资金幂等）。

同一 (user, key) 的资金操作重复提交时直接返回首次结果，避免网络重试导致重复扣款。
参照 Stripe：记录请求指纹（scope + 参数哈希）；同 key 但参数/操作不同 → 冲突拒绝，
杜绝「复用旧 key 提交新金额被静默吞掉」与「同 key 跨操作串味」两类隐患。

V130（104 号 spec）补的三件：

- **先占键，再动钱**（FIN-072）。原来是「查 → 跑 → 记」：两个同键请求并发时
  都查不到、**都把钱动了一遍**，后一个记录时撞唯一约束而 500，靠整个事务回滚
  才没多入账。用户看到的是钱包页上的「服务器错误」，而且不知道钱动没动。
  现在先 `INSERT ... ON CONFLICT DO NOTHING` 占键：后到的那个在唯一索引上等
  前一个提交，插入落空，然后读到它的结果原样回放——**钱只动一次，两个人都拿到
  同一个 200**。

  为什么不用 V112 钱包那样的 SAVEPOINT：pysqlite 不会在 SAVEPOINT 之前发 BEGIN，
  占键是这个事务的第一笔写入时，RELEASE 就等于提交——空结果的占位行**在动钱之前
  就落库了**，并发的人读到空结果，动钱失败时占位也不随之回滚。V130 第一版就是
  这么写的，测试当场红了。ON CONFLICT 不需要 SAVEPOINT，也不毒化外层事务。
- **记录会过期**（FIN-071）。Stripe 的语义是 24 小时；没有过期的表会无限增长。
  过期判断在**读的时候**就生效（不靠清理 job 准时跑），job 只负责把行删掉。
- **键的长度在入口校验**。原来存的是 `key[:80]` 而查的是完整的 key——
  超过 80 个字符的键**永远查不到自己的记录**，每次重试都重跑一遍再撞约束。
"""
import hashlib
import json
from datetime import timedelta

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import settings
from app.core.db import Base
from app.core.errors import bad_request, conflict
from app.modules.account.models import utcnow

# 与开放 API 的机器写操作同一个上限（openapi/machine.py）
MAX_KEY_LENGTH = 80


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


def _cutoff():
    return utcnow() - timedelta(hours=settings.IDEMPOTENCY_RETENTION_HOURS)


def require_key(key: str | None) -> str:
    """资金类写操作：键必须有，且不超过上限。

    「资金类强制」写在 14.6 里，而服务端此前把空键当成「不要幂等」直接执行，
    两端的 SDK 也从来没有发过这个头——**这条保护对真实用户一次都没有生效过**。
    强制之后，一个忘了带键的新客户端会在开发时就拿到 400，而不是上线后
    悄悄地把双击变成两笔充值。
    """
    if not key:
        raise bad_request("资金操作必须携带 Idempotency-Key（防止重试导致重复扣款）",
                          "idempotency_required")
    if len(key) > MAX_KEY_LENGTH:
        raise bad_request(f"Idempotency-Key 至多 {MAX_KEY_LENGTH} 个字符", "idempotency_key_invalid")
    return key


def _replay(record: IdempotencyRecord, fp: str):
    if record.fingerprint and record.fingerprint != fp:
        raise conflict(
            "幂等键已用于不同的请求，请更换 Idempotency-Key", "idempotency_key_conflict"
        )
    return json.loads(record.response)


def _find(db: Session, user_id: int, key: str) -> IdempotencyRecord | None:
    return (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
        .first()
    )


def replay_or_run(db: Session, user_id: int, key: str | None, scope: str, run,
                  params: dict | None = None):
    """key 为空则直接执行；否则命中且指纹一致返回旧结果，未命中先占键、再执行、再记结果。

    同 key 但 (scope, params) 指纹不同 → 409 idempotency_key_conflict（防串味/防吞单）。
    run() 必须返回可 JSON 序列化的 dict；它抛异常时整个请求回滚，占的键也随之消失
    （失败不缓存——客户端用同一个键重试会真的再试一次）。
    """
    if not key:
        return run()
    if len(key) > MAX_KEY_LENGTH:
        raise bad_request(f"Idempotency-Key 至多 {MAX_KEY_LENGTH} 个字符", "idempotency_key_invalid")
    fp = _fingerprint(scope, params)

    existing = _find(db, user_id, key)
    if existing is not None and existing.created_at < _cutoff():
        # 过期了：与清理 job 同一个判断。删掉旧的，这个键当作新的用
        db.delete(existing)
        db.flush()
        existing = None
    if existing is not None:
        return _replay(existing, fp)

    if not _claim(db, user_id, key, scope, fp):
        # 同一个键的另一个请求先占了，并且已经提交（Postgres 上这次插入会一直
        # 等到它提交或回滚；它回滚的话这里插入就成功了，走不到这儿）。
        other = _find(db, user_id, key)
        if other is not None and other.response:
            return _replay(other, fp)
        # 读到了却没有结果，或者刚好被清理掉：不猜，让客户端用同一个键再试
        raise conflict("同一个 Idempotency-Key 的请求正在处理，请稍后用同一个键重试",
                       "idempotency_in_progress")

    result = run()
    (db.query(IdempotencyRecord)
     .filter(IdempotencyRecord.user_id == user_id, IdempotencyRecord.key == key)
     .update({"response": json.dumps(result, ensure_ascii=False)}, synchronize_session=False))
    return result


def _claim(db: Session, user_id: int, key: str, scope: str, fp: str) -> bool:
    """占键：插入成功返回 True；同键已存在（含刚被并发请求提交的）返回 False。"""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - 只支持这两种库（DEP-020）
        raise RuntimeError(f"不支持的数据库方言：{dialect}")
    table = IdempotencyRecord.__table__
    stmt = (insert(table)
            .values(user_id=user_id, key=key, scope=scope, fingerprint=fp, response="",
                    created_at=utcnow())
            .on_conflict_do_nothing(index_elements=["user_id", "key"])
            .returning(table.c.id))
    # 用 RETURNING 判断插入是否落空，**不用 rowcount**：V130 第一版用的是 rowcount，
    # SQLite 上是 1，在 Postgres（psycopg）上不是——于是**每一笔**充值都被当成
    # 「别人先占了」而 409。SQLite 测试全绿，生产上充值提现会全部失败。
    # 是在本地起了一个 Postgres 跑同一组测试才看到的。
    return db.execute(stmt).first() is not None


def purge(db: Session) -> dict:
    """FIN-071 删掉过期的幂等记录。过期判断与 `replay_or_run` 同一个 `_cutoff()`。"""
    n = (db.query(IdempotencyRecord)
         .filter(IdempotencyRecord.created_at < _cutoff())
         .delete(synchronize_session=False))
    return {"purged": n, "retention_hours": settings.IDEMPOTENCY_RETENTION_HOURS}
