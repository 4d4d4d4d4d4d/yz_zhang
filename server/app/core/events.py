"""进程内领域事件总线（14 号 spec 第 3 节的 MVP 实现）。

同步派发；生产演进方向是替换为 Kafka/RocketMQ，发布方接口保持不变。
handler 签名: fn(db: Session, payload: dict) -> None
"""
from collections import defaultdict
from typing import Callable

_handlers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event: str, handler: Callable) -> None:
    if handler not in _handlers[event]:
        _handlers[event].append(handler)


def publish(db, event: str, payload: dict) -> None:
    for handler in list(_handlers[event]):
        handler(db, payload)
