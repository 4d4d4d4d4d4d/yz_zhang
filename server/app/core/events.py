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


_handlers: dict[str, list[Subscription]] = defaultdict(list)


def subscribe(event: str, handler: Callable, *, retry: bool, critical: bool = False) -> None:
    """注册订阅者。

    `retry` 是**必填关键字参数**，问的不是「幂等吗」而是
    「失败后隔一段时间自动补做，还对吗」——有了 SAVEPOINT，失败的写入
    已经回滚干净，纯 DB handler 几乎自动可重试；真正的问题是**时序**。
    写成必填参数，是为了拦住下一个新增 handler 的人（包括未来的我）
    在没想清楚之前就把它挂上去。

    `critical=True` 表示这个副作用缺失会让已提交的业务事实无法自圆其说
    （如存证入链），失败必须让整笔业务事务失败。
    """
    name = f"{handler.__module__}.{handler.__qualname__}"
    if any(s.name == name for s in _handlers[event]):
        return
    _handlers[event].append(
        Subscription(handler=handler, name=name, retry=retry, critical=critical)
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


# ---------- EVT-021 跨副本补做 ----------
def _subscription(event: str, name: str) -> Subscription | None:
    return next((s for s in _handlers[event] if s.name == name), None)


def drain(db, limit: int = 50) -> dict:
    """重试失败且可重试的投递。任何副本都能补做任何副本发布的事件。

    每条用**独立事务**（保存点 + 逐条提交）：一条重试失败不影响其它条。
    """
    import json

    rows = (
        db.query(EventDelivery)
        .filter(EventDelivery.status == "failed")
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
         "at": r.updated_at.isoformat()}
        for r in rows
    ]
