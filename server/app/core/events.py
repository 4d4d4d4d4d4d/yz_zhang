"""领域事件投递：同步派发 + 失败隔离 + 事务性发件箱（28 号 spec）。

原实现十七行、同步、无隔离——`task.completed` 上挂着 6 个 handler，
任何一个抛异常都会把**验收放款整笔回滚**。已用探针复现：
知识卡片生成失败（走 LLM，超时很正常）→ 执行方拿不到钱。
知识库是锦上添花，放款是这个平台的存在理由，不能让前者拖死后者。

现在的模型：
- `publish()` 在业务事务内写一条 `OutboxEvent`（与业务改动同生共死）；
- 每个 handler 在 **SAVEPOINT** 里跑，失败只回滚它自己那一段；
- 每次投递结果写 `EventDelivery`，`(event_id, handler)` 唯一——
  这个唯一约束就是「恰好一次」的实现，跨副本同样成立；
- 失败且 `retry=True` 的，由 drain job 在**任何副本**上补做（SEC-040）；
  `retry=False` 的直接进死信等人处理。

handler 签名: fn(db: Session, payload: dict) -> None
"""
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from app.core.timefmt import iso

logger = logging.getLogger("app.events")

MAX_ATTEMPTS = 5
RETENTION_DAYS = 14


def _utcnow() -> datetime:
    from app.modules.account.models import utcnow

    return utcnow()


class OutboxEvent(Base):
    """EVT-001 已发布的事件。写在业务事务里：业务回滚则它不存在。"""

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String(48), index=True)
    # JSON 文本；EVT-003 只放标识符，不放业务对象快照——
    # 重试时 handler 重新读库，拿到的是当下的真实状态而不是发布时的陈旧副本
    payload: Mapped[str] = mapped_column(Text, default="{}")
    # 发布副本，排查「只有某个副本出问题」时的第一手线索
    instance: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class EventDelivery(Base):
    """EVT-002 一个 handler 对一条事件的投递结果。

    `(event_id, handler)` 唯一 —— 恰好一次不是靠代码自觉，是靠这个约束。
    """

    __tablename__ = "event_deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "handler", name="uq_delivery_event_handler"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, index=True)
    event: Mapped[str] = mapped_column(String(48), index=True)
    handler: Mapped[str] = mapped_column(String(120), index=True)
    # done / failed / dead
    status: Mapped[str] = mapped_column(String(12), default="done", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    last_error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


@dataclass(frozen=True)
class Subscription:
    handler: Callable
    name: str
    retry: bool
    critical: bool
    after_commit: bool = False


_handlers: dict[str, list[Subscription]] = defaultdict(list)


def subscribe(event: str, handler: Callable, *, retry: bool, critical: bool = False,
              after_commit: bool = False) -> None:
    """注册订阅者。

    `retry` 是**必填关键字参数**，问的不是「幂等吗」而是
    「失败后隔一段时间自动补做，还对吗」——有了 SAVEPOINT，失败的写入
    已经回滚干净，纯 DB handler 几乎自动可重试；真正的问题是**时序**。
    写成必填参数，是为了拦住下一个新增 handler 的人（包括未来的我）
    在没想清楚之前就把它挂上去。

    `critical=True` 表示这个副作用缺失会让已提交的业务事实无法自圆其说
    （如存证入链），失败必须让整笔业务事务失败。

    `after_commit=True`（CONC-067）：handler 要调外部服务（推送、短信……）。它**不在业务事务里跑**——
    业务提交之后另开会话投递；业务回滚了就根本不投递（此前回滚的那笔放款也会照样推一条「已到账」）；
    提交之后、投递之前进程挂了，投递记录停在 `deferred`，drain job 过一会儿补做。
    """
    if after_commit and (critical or not retry):
        raise ValueError("after_commit 的 handler 必须 retry=True 且不能是 critical：它在业务提交之后才跑")
    name = f"{handler.__module__}.{handler.__qualname__}"
    if any(s.name == name for s in _handlers[event]):
        return
    _handlers[event].append(
        Subscription(handler=handler, name=name, retry=retry, critical=critical,
                     after_commit=after_commit)
    )


def publish(db, event: str, payload: dict) -> None:
    """写发件箱 + 逐个 handler 隔离派发。"""
    import json

    from app.core.locks import INSTANCE_ID

    row = OutboxEvent(event=event, payload=json.dumps(payload, ensure_ascii=False, default=str),
                      instance=INSTANCE_ID)
    db.add(row)
    db.flush()
    for sub in list(_handlers[event]):
        _dispatch(db, row.id, event, payload, sub)


def _dispatch(db, event_id: int, event: str, payload: dict, sub: Subscription) -> None:
    if sub.after_commit:
        _record(db, event_id, event, sub.name, "deferred", error="")
        db.info.setdefault("deferred_events", []).append((event_id, sub.name))
        return
    if sub.critical:
        # EVT-012 不隔离：它不是「副作用」，是业务本身，失败就该整笔失败
        sub.handler(db, payload)
        _record(db, event_id, event, sub.name, "done")
        return
    savepoint = db.begin_nested()
    try:
        sub.handler(db, payload)
        savepoint.commit()
    except Exception as exc:  # noqa: BLE001 — 隔离是本函数的全部目的
        savepoint.rollback()
        # EVT-011 绝不静默：失败必须留痕，否则「崩掉」只是变成了「悄悄丢失」
        logger.warning(
            "event_handler_failed", extra={"event": event, "handler": sub.name,
                                           "error": type(exc).__name__},
        )
        _record(db, event_id, event, sub.name, "failed" if sub.retry else "dead",
                error=f"{type(exc).__name__}: {exc}"[:900])
    else:
        _record(db, event_id, event, sub.name, "done")


def _record(db, event_id: int, event: str, handler: str, status: str, error: str = "") -> None:
    """投递结果写在**业务会话**里：业务最终回滚了，这条记录也不该留下。"""
    row = (
        db.query(EventDelivery)
        .filter(EventDelivery.event_id == event_id, EventDelivery.handler == handler)
        .first()
    )
    if row is None:
        row = EventDelivery(event_id=event_id, event=event, handler=handler,
                            status=status, attempts=1, last_error=error)
    else:
        row.status = status
        row.attempts += 1
        row.last_error = error
    row.updated_at = _utcnow()
    db.add(row)
    db.flush()


# ---------- CONC-067 业务提交之后再投递 ----------
DEFERRED_GRACE_SECONDS = 60


def _deliver_deferred(event_id: int, handler_name: str) -> None:
    """另开会话投递一条 after_commit 的事件。失败留给 drain，**绝不抛回业务**（业务已经提交了）。"""
    import json

    from .db import SessionLocal

    with SessionLocal() as db:
        try:
            row = (db.query(EventDelivery)
                   .filter(EventDelivery.event_id == event_id, EventDelivery.handler == handler_name,
                           EventDelivery.status == "deferred").first())
            event_row = db.get(OutboxEvent, event_id) if row is not None else None
            sub = _subscription(row.event, handler_name) if row is not None else None
            if row is None or event_row is None or sub is None:
                return
            payload = json.loads(event_row.payload or "{}")
            try:
                sub.handler(db, payload)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                row = db.get(EventDelivery, row.id)
                row.status, row.last_error = "failed", f"{type(exc).__name__}: {exc}"[:900]
                logger.warning("event_handler_failed",
                               extra={"event": row.event, "handler": handler_name, "error": type(exc).__name__})
            else:
                row.status, row.last_error = "done", ""
            row.updated_at = _utcnow()
            db.add(row)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("deferred_event_delivery_crashed")


def install_after_commit(session_factory) -> None:
    """在会话工厂上挂「提交之后投递」与「回滚就作废」。重复调用无害。"""
    from sqlalchemy import event as sa_event

    if getattr(session_factory, "_deferred_events_installed", False):
        return
    session_factory._deferred_events_installed = True

    @sa_event.listens_for(session_factory, "after_commit")
    def _after_commit(session):  # noqa: ANN001
        # 保存点释放时这个事件也会触发（实测：handler 的 SAVEPOINT 一提交就到这里，外层事务还开着，
        # 新会话根本看不见刚写的投递记录）。只有外层也结束了才是真的「业务已提交」
        if session.get_nested_transaction() is not None:
            return
        pending = session.info.pop("deferred_events", [])
        for event_id, handler_name in pending:
            _deliver_deferred(event_id, handler_name)
        for label, fn in session.info.pop("on_commit", []):
            try:
                fn()
            except Exception:  # noqa: BLE001 - 业务已经提交，副作用失败只记日志
                logger.exception("on_commit_failed", extra={"handler": label})

    @sa_event.listens_for(session_factory, "after_soft_rollback")
    def _after_rollback(session, previous_transaction):  # noqa: ANN001
        # 只有**最外层**回滚才作废：某个 handler 的保存点回滚，不能把别的 handler 排好的推送一起丢掉
        # （保存点里排的那几条，它们的投递记录已随保存点回滚，投递时找不到记录会自动跳过）
        if previous_transaction.parent is None and not previous_transaction.nested:
            session.info.pop("deferred_events", None)
            session.info.pop("on_commit", None)


def on_commit(db, label: str, fn) -> None:
    """CONC-067 业务提交之后再做的外部副作用（删存储里的文件……）。业务回滚了就不做。

    与 after_commit 订阅者的区别：这里**不重试、不留痕**——只用于「做不成也只是多留一个
    孤儿文件」这一类；要可靠送达的走事件（`subscribe(..., after_commit=True)`）。
    """
    db.info.setdefault("on_commit", []).append((label, fn))


# ---------- EVT-021 跨副本补做 ----------
def _subscription(event: str, name: str) -> Subscription | None:
    return next((s for s in _handlers[event] if s.name == name), None)


def drain(db, limit: int = 50) -> dict:
    """重试失败且可重试的投递。任何副本都能补做任何副本发布的事件。

    每条用**独立事务**（保存点 + 逐条提交）：一条重试失败不影响其它条。
    """
    import json

    from sqlalchemy import and_, or_

    stale = _utcnow() - timedelta(seconds=DEFERRED_GRACE_SECONDS)
    rows = (
        db.query(EventDelivery)
        # deferred 且放了一阵子：业务提交之后、投递之前进程挂了
        .filter(or_(EventDelivery.status == "failed",
                    and_(EventDelivery.status == "deferred", EventDelivery.updated_at < stale)))
        .order_by(EventDelivery.id)
        .limit(limit)
        .all()
    )
    retried = recovered = dead = 0
    for row in rows:
        sub = _subscription(row.event, row.handler)
        if sub is None:
            # 代码里已经没有这个 handler 了（改名/下线），继续重试没有意义
            row.status = "dead"
            row.last_error = "handler_not_registered"
            db.add(row)
            dead += 1
            continue
        if not sub.retry:  # 理论上不该出现，防御性处理
            row.status = "dead"
            db.add(row)
            dead += 1
            continue
        event_row = db.get(OutboxEvent, row.event_id)
        if event_row is None:
            row.status = "dead"
            row.last_error = "outbox_event_missing"
            db.add(row)
            dead += 1
            continue
        retried += 1
        payload = json.loads(event_row.payload or "{}")
        if sub.after_commit:
            # 这类 handler 调外部服务：先把前面各条的状态提交，不挂着事务、也不开保存点（CONC-067）
            from app.vendors.base import checkpoint

            checkpoint(db, "事件补做：每条投递是自己的事务，前面各条的状态已经一致")
            row_id = row.id
            try:
                sub.handler(db, payload)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                row = db.get(EventDelivery, row_id)
                row.attempts += 1
                row.last_error = f"{type(exc).__name__}: {exc}"[:900]
                row.status = "dead" if row.attempts >= MAX_ATTEMPTS else "failed"
                dead += 1 if row.status == "dead" else 0
            else:
                row = db.get(EventDelivery, row_id)
                row.status, row.last_error = "done", ""
                row.attempts += 1
                recovered += 1
            row.updated_at = _utcnow()
            db.add(row)
            db.commit()
            continue
        savepoint = db.begin_nested()
        try:
            sub.handler(db, payload)
            savepoint.commit()
        except Exception as exc:  # noqa: BLE001
            savepoint.rollback()
            row.attempts += 1
            row.last_error = f"{type(exc).__name__}: {exc}"[:900]
            # EVT-023 到顶转死信，避免无限重试打爆日志与数据库
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "dead"
                dead += 1
        else:
            row.status = "done"
            row.attempts += 1
            row.last_error = ""
            recovered += 1
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
    return {"scanned": len(rows), "retried": retried, "recovered": recovered, "dead": dead}


def purge(db, days: int = RETENTION_DAYS) -> dict:
    """EVT-004 清理已完成的旧事件；失败与死信**不删**。"""
    cutoff = _utcnow() - timedelta(days=days)
    old_ids = [
        r.id for r in db.query(OutboxEvent.id).filter(OutboxEvent.created_at < cutoff)
    ]
    if not old_ids:
        return {"deleted": 0, "kept_unfinished": 0}
    unfinished = {
        r.event_id for r in db.query(EventDelivery.event_id).filter(
            EventDelivery.event_id.in_(old_ids), EventDelivery.status != "done",
        )
    }
    removable = [i for i in old_ids if i not in unfinished]
    if removable:
        db.query(EventDelivery).filter(EventDelivery.event_id.in_(removable)).delete(
            synchronize_session=False
        )
        db.query(OutboxEvent).filter(OutboxEvent.id.in_(removable)).delete(
            synchronize_session=False
        )
    return {"deleted": len(removable), "kept_unfinished": len(unfinished)}


def health(db) -> dict:
    """EVT-030/031 待重试与死信统计。死信堆积是「有功能已经悄悄坏了」的最早信号。"""
    rows = db.query(EventDelivery).filter(EventDelivery.status != "done").all()
    by_handler: dict[str, dict] = {}
    for row in rows:
        slot = by_handler.setdefault(row.handler, {"failed": 0, "dead": 0, "last_error": ""})
        slot[row.status] = slot.get(row.status, 0) + 1
        slot["last_error"] = row.last_error or slot["last_error"]
    return {
        "pending_retry": sum(1 for r in rows if r.status == "failed"),
        # 业务已提交、等着提交后投递的（CONC-067）；长时间不降说明投递挂了，drain 会补
        "deferred": sum(1 for r in rows if r.status == "deferred"),
        "dead_letters": sum(1 for r in rows if r.status == "dead"),
        "by_handler": by_handler,
    }


def dead_letters(db, limit: int = 100) -> list[dict]:
    rows = (
        db.query(EventDelivery)
        .filter(EventDelivery.status == "dead")
        .order_by(EventDelivery.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {"id": r.id, "event": r.event, "event_id": r.event_id, "handler": r.handler,
         "attempts": r.attempts, "last_error": r.last_error,
         "at": iso(r.updated_at)}
        for r in rows
    ]


def _install_default() -> None:
    from .db import SessionLocal

    install_after_commit(SessionLocal)


_install_default()
