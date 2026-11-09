"""节点间 gossip 日志同步（L3 层，REQ-NW-003）。

协议：比较对方日志长度 → 校验共同前缀的末尾哈希一致（否则为分叉）→ 拉取缺失事件 →
逐条通过 `apply_event` 重新执行，并要求本地生成的事件哈希与对方完全一致。
也就是说，同步方不是“相信”对方的状态，而是**自己重新计算一遍**并比对。

当前限制：只支持“单写者 / 线性扩展”的同步；两个节点各自写入导致分叉时报 ForkError，
多写者场景请使用 mesh.py（签名操作 G-Set + epoch 确定性折叠，REQ-FD-005）。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol

from .node import SignalNode
from .store import event_from_dict, event_to_dict


class SyncError(RuntimeError):
    pass


class ForkError(SyncError):
    pass


class Peer(Protocol):
    def head(self) -> dict[str, Any]: ...

    def events(self, after: int) -> list[dict[str, Any]]: ...


class LocalPeer:
    def __init__(self, node: SignalNode) -> None:
        self.node = node

    def head(self) -> dict[str, Any]:
        return {"len": len(self.node.ledger), "head": self.node.ledger.head}

    def events(self, after: int) -> list[dict[str, Any]]:
        return [event_to_dict(e) for e in list(self.node.ledger)[after:]]


class HttpPeer:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Any:
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def head(self) -> dict[str, Any]:
        return self._get("/head")

    def events(self, after: int) -> list[dict[str, Any]]:
        return self._get(f"/events?after={after}")


def pull(node: SignalNode, peer: Peer) -> int:
    """从 peer 拉取并验证缺失事件，返回新增条数。"""
    mine = len(node.ledger)
    theirs = int(peer.head()["len"])
    if mine > 0:
        overlap = peer.events(mine - 1)
        if not overlap:
            if theirs < mine:
                return 0  # 对方落后，由对方来拉取
            raise SyncError("对方未返回共同前缀")
        if overlap[0]["hash"] != node.ledger.head:
            raise ForkError("日志分叉：共同前缀的末尾哈希不一致")
        incoming = overlap[1:]
    else:
        incoming = peer.events(0)
    added = 0
    for d in incoming:
        ev = event_from_dict(d)
        if ev.seq != len(node.ledger) or ev.prev_hash != node.ledger.head:
            raise SyncError(f"事件序号/前驱不连续：seq={ev.seq}")
        node.apply_event(ev)
        got = list(node.ledger)[-1]
        if got.hash != ev.hash:
            raise SyncError(f"重新执行 seq={ev.seq} 得到的事件与对方不一致（对方状态无效）")
        added += 1
    return added
