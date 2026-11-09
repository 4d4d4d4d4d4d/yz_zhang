"""多写者联邦（L3 层，REQ-FD-005）。

问题：线性 gossip（sync.py）只允许一个写者，两个节点各自接收用户操作就会分叉。

方案：节点之间不交换“状态”，只交换**用户签名的操作**（发布、承诺、揭示、记录、曝光回执……）
构成一个只增集合（G-Set），再按 epoch **确定性折叠**出状态：

    state = fold( sorted(ops, key=(有效 epoch, epoch 内时间, 类型优先级, op_id)) )

- 集合相同 ⇒ 状态与日志 head 完全相同（与接收顺序、来源节点无关），天然收敛。
- 有效 epoch：每个收到操作的节点签一份“见证”（我在第几个 epoch 收到它）；
  按时到达（epoch 结束 + 宽限期之前）记为声明的 epoch，迟到记为到达时的 epoch。
  有效 epoch = 见证 epoch（裁剪到 [声明, 声明+24]）的上中位数。
  ⇒ 倒填时间最多回溯一个宽限期；只要诚实节点不少于见证的一半，作恶节点无法把操作“提前”，
    最多把它推后 24 个 epoch。
- 折叠在 epoch 封存（结束时间 <= until）后才包含该 epoch；每个 epoch 末尾执行一次 tick。
- 无效操作（签名错、业务规则拒绝）在折叠时被确定性地跳过，所有节点跳过同一批。

限制：每次查询状态都从头折叠（O(全部操作)），生产实现需要按已封存 epoch 做检查点。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import ads, attestation, content, crypto, records
from .node import NodeConfig, SignalNode

# 同一时刻内的执行顺序：先身份/广告设置，再发布，再承诺，再揭示，最后曝光
KIND_RANK = {"record": 0, "campaign": 0, "publish": 1, "commit": 2, "reveal": 3, "view": 4}


class MeshError(ValueError):
    pass


@dataclass(frozen=True)
class Op:
    kind: str
    payload: dict[str, Any]
    now: int

    @property
    def id(self) -> str:
        return crypto.content_hash({"kind": self.kind, "payload": self.payload, "now": self.now})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "payload": self.payload, "now": self.now}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Op:
        return cls(d["kind"], d["payload"], int(d["now"]))


def op_publish(c: content.Content, now: int) -> Op:
    return Op("publish", c.to_dict(), now)


def op_commit(cm: attestation.Commit, now: int) -> Op:
    return Op("commit", cm.to_dict(), now)


def op_reveal(a: attestation.Attestation, salt: str, now: int) -> Op:
    return Op("reveal", {"att": a.to_dict(), "salt": salt}, now)


def op_record(r: records.Record, now: int) -> Op:
    return Op("record", r.to_dict(), now)


def op_view(r: records.Record, now: int) -> Op:
    return Op("view", r.to_dict(), now)


def op_campaign(c: ads.Campaign, now: int) -> Op:
    return Op(
        "campaign",
        {
            "campaign_id": c.campaign_id,
            "advertiser": c.advertiser,
            "budget_micros": c.budget_micros,
            "cpm_micros": c.cpm_micros,
            "tags": list(c.tags),
        },
        now,
    )


def precheck(op: Op) -> None:
    """只依赖操作本身的廉价校验（签名、结构）。结果对所有节点相同。"""
    try:
        p = op.payload
        if op.kind == "publish":
            ok = content.Content.from_dict(p).verify()
        elif op.kind == "commit":
            ok = attestation.Commit.from_dict(p).verify()
        elif op.kind == "reveal":
            ok = attestation.Attestation.from_dict(p["att"]).verify() and isinstance(p["salt"], str)
        elif op.kind in ("record", "view"):
            ok = records.Record.from_dict(p).verify()
        elif op.kind == "campaign":
            ok = int(p["budget_micros"]) > 0
        else:
            ok = False
    except (KeyError, TypeError, ValueError) as e:
        raise MeshError(f"操作格式错误: {e}") from e
    if not ok:
        raise MeshError("操作签名无效")


@dataclass(frozen=True)
class Witness:
    op_id: str
    epoch: int
    node: str  # 见证节点 DID
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {"type": "witness/v1", "op_id": self.op_id, "epoch": self.epoch, "node": self.node}

    def verify(self) -> bool:
        return crypto.verify(self.node, self.payload(), self.signature)


class MeshNode:
    def __init__(
        self,
        name: str,
        *,
        epoch_s: int = 3600,
        grace_s: int = 600,
        max_delay_epochs: int = 24,
        config_factory: Callable[[], NodeConfig] = NodeConfig,
    ) -> None:
        self.max_delay_epochs = max_delay_epochs
        self.name = name
        self.identity = crypto.Identity.from_seed(f"mesh-node:{name}".encode())
        self.epoch_s = epoch_s
        self.grace_s = grace_s
        self.config_factory = config_factory
        self.ops: dict[str, Op] = {}
        self.witnesses: dict[str, dict[str, Witness]] = {}
        self.rejected: set[str] = set()

    @property
    def did(self) -> str:
        return self.identity.did

    # ---- 接收与 gossip ----
    def receive(self, op: Op, local_now: int) -> str:
        precheck(op)
        claimed = op.now // self.epoch_s
        on_time = local_now < (claimed + 1) * self.epoch_s + self.grace_s
        epoch = claimed if on_time else local_now // self.epoch_s
        self.ops.setdefault(op.id, op)
        mine = self.witnesses.setdefault(op.id, {})
        if self.did not in mine:
            w = Witness(op.id, epoch, self.did)
            mine[self.did] = Witness(op.id, epoch, self.did, self.identity.sign(w.payload()))
        return op.id

    def merge(self, ops: list[dict[str, Any]], witnesses: list[dict[str, Any]]) -> int:
        added = 0
        for d in ops:
            op = Op.from_dict(d)
            if op.id in self.ops:
                continue
            precheck(op)
            self.ops[op.id] = op
            added += 1
        for d in witnesses:
            w = Witness(d["op_id"], int(d["epoch"]), d["node"], d["signature"])
            if w.op_id in self.ops and w.verify():
                self.witnesses.setdefault(w.op_id, {}).setdefault(w.node, w)
        return added

    def export(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        ops = [op.to_dict() for _, op in sorted(self.ops.items())]
        ws = [
            {"op_id": w.op_id, "epoch": w.epoch, "node": w.node, "signature": w.signature}
            for _, per in sorted(self.witnesses.items())
            for _, w in sorted(per.items())
        ]
        return ops, ws

    def gossip(self, other: MeshNode) -> int:
        """双向交换操作与见证，返回双方新增操作总数。"""
        a_ops, a_ws = self.export()
        b_ops, b_ws = other.export()
        return other.merge(a_ops, a_ws) + self.merge(b_ops, b_ws)

    # ---- 折叠 ----
    def effective_epoch(self, op_id: str) -> int:
        """见证 epoch 先裁剪到 [声明 epoch, 声明 + max_delay_epochs]，再取上中位数。

        上中位数：见证数为偶数时取较晚者——宁可把操作推后，也不让少数节点把它提前（防倒填）。
        裁剪：作恶节点谎称“很晚才收到”最多把操作推后 max_delay_epochs 个 epoch。
        """
        op = self.ops[op_id]
        claimed = op.now // self.epoch_s
        epochs = sorted(
            min(max(w.epoch, claimed), claimed + self.max_delay_epochs)
            for w in self.witnesses.get(op_id, {}).values()
        )
        if not epochs:
            return claimed
        return epochs[len(epochs) // 2]

    def set_digest(self) -> str:
        """操作集合 + 有效 epoch 的摘要：两节点相等 ⇒ 折叠结果相等。"""
        return crypto.content_hash(
            sorted([op_id, self.effective_epoch(op_id)] for op_id in self.ops)
        )

    def state(self, until: int) -> SignalNode:
        node = SignalNode("mesh", config=self.config_factory())
        self.rejected = set()
        by_epoch: dict[int, list[str]] = {}
        for op_id in self.ops:
            by_epoch.setdefault(self.effective_epoch(op_id), []).append(op_id)
        if not by_epoch:
            return node
        last_sealed = until // self.epoch_s - 1
        for e in range(min(by_epoch), last_sealed + 1):
            start, end = e * self.epoch_s, (e + 1) * self.epoch_s
            ordered = sorted(
                by_epoch.get(e, []),
                key=lambda i: (
                    min(max(self.ops[i].now, start), end - 1),
                    KIND_RANK[self.ops[i].kind],
                    i,
                ),
            )
            for op_id in ordered:
                op = self.ops[op_id]
                t = min(max(op.now, start), end - 1)
                try:
                    _apply(node, op, t)
                except (ValueError, RuntimeError, KeyError):
                    self.rejected.add(op_id)  # 所有节点都会以同样方式跳过
            node.tick(end)
        return node


def _apply(node: SignalNode, op: Op, t: int) -> None:
    p = op.payload
    if op.kind == "publish":
        node.publish(content.Content.from_dict(p), t)
    elif op.kind == "commit":
        node.commit(attestation.Commit.from_dict(p), t)
    elif op.kind == "reveal":
        node.reveal(attestation.Attestation.from_dict(p["att"]), p["salt"], t)
    elif op.kind == "record":
        node.submit(records.Record.from_dict(p), t)
    elif op.kind == "view":
        node.view_receipt(records.Record.from_dict(p), t)
    elif op.kind == "campaign":
        node.add_campaign(
            ads.Campaign(
                p["campaign_id"],
                p["advertiser"],
                p["budget_micros"],
                p["cpm_micros"],
                tuple(p["tags"]),
            )
        )
