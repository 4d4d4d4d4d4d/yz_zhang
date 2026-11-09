"""SQLite 持久化（L3 层，REQ-NW-002）。

只持久化哈希链日志：节点状态 = 日志重放结果，因此“重启后状态一致”等价于“日志完整且可重放”。
加载时逐条校验哈希链，任何篡改都会导致加载失败。
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ledger import Event, LedgerError
from .node import SignalNode

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def event_to_dict(ev: Event) -> dict[str, Any]:
    return {
        "seq": ev.seq,
        "kind": ev.kind,
        "data": ev.data,
        "prev_hash": ev.prev_hash,
        "hash": ev.hash,
    }


def event_from_dict(d: dict[str, Any]) -> Event:
    return Event(int(d["seq"]), d["kind"], d["data"], d["prev_hash"], d["hash"])


class SQLiteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def persist(self, node: SignalNode) -> int:
        """把节点日志中尚未落盘的事件写入数据库，返回写入条数。"""
        have = self.count()
        evs = list(node.ledger)[have:]
        with self.db:
            self.db.executemany(
                "INSERT INTO events (seq, kind, data, prev_hash, hash) VALUES (?, ?, ?, ?, ?)",
                [
                    (e.seq, e.kind, json.dumps(e.data, ensure_ascii=False), e.prev_hash, e.hash)
                    for e in evs
                ],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('node_id', ?)", (node.node_id,)
            )
        return len(evs)

    def events(self) -> list[Event]:
        rows = self.db.execute(
            "SELECT seq, kind, data, prev_hash, hash FROM events ORDER BY seq"
        ).fetchall()
        out = []
        prev = "0" * 64
        for seq, kind, data, prev_hash, h in rows:
            ev = Event(seq, kind, json.loads(data), prev_hash, h)
            if ev.prev_hash != prev or Event.compute_hash(seq, kind, ev.data, prev_hash) != h:
                raise LedgerError(f"数据库中的日志在 seq={seq} 处被篡改")
            out.append(ev)
            prev = h
        return out

    def load(self, node_id: str = "", **kwargs: Any) -> SignalNode:
        row = self.db.execute("SELECT value FROM meta WHERE key='node_id'").fetchone()
        nid = node_id or (row[0] if row else "node")
        return SignalNode.replay(self.events(), nid, **kwargs)
