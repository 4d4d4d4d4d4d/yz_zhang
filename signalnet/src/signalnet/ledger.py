"""仅追加、哈希链式的事件日志（L0 层）。

所有影响声誉、分发和收益的事件都写入日志；任何节点可以重放日志并得到完全相同的状态
（REQ-FD-002 可验证性）。日志不是区块链，不发币，只用于可审计。

相关需求：REQ-LG-001, REQ-LG-002
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from . import crypto

GENESIS = "0" * 64


@dataclass(frozen=True)
class Event:
    seq: int
    kind: str
    data: dict[str, Any]
    prev_hash: str
    hash: str

    @staticmethod
    def compute_hash(seq: int, kind: str, data: dict[str, Any], prev_hash: str) -> str:
        return crypto.content_hash({"seq": seq, "kind": kind, "data": data, "prev": prev_hash})


class LedgerError(RuntimeError):
    pass


class Ledger:
    def __init__(self) -> None:
        self._events: list[Event] = []

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    @property
    def head(self) -> str:
        return self._events[-1].hash if self._events else GENESIS

    def append(self, kind: str, data: dict[str, Any]) -> Event:
        # 通过规范化编码做一次深拷贝，防止调用方事后修改 data 破坏哈希
        frozen = json.loads(crypto.canonical(data))
        seq = len(self._events)
        h = Event.compute_hash(seq, kind, frozen, self.head)
        ev = Event(seq, kind, frozen, self.head, h)
        self._events.append(ev)
        return ev

    def verify_chain(self) -> bool:
        prev = GENESIS
        for i, ev in enumerate(self._events):
            if ev.seq != i or ev.prev_hash != prev:
                return False
            if Event.compute_hash(ev.seq, ev.kind, ev.data, ev.prev_hash) != ev.hash:
                return False
            prev = ev.hash
        return True

    def of_kind(self, kind: str) -> list[Event]:
        return [e for e in self._events if e.kind == kind]
