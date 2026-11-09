"""联邦节点与反垄断路由（L2 层）。

允许存在“枢纽节点（hub）”提升索引/转码/分发效率，但：
- 单个 hub 在一个结算周期内承担的流量份额不得超过 max_hub_share（REQ-FD-001）；
- hub 无权修改共识——共识只由签名评审计算，任何节点可复算（REQ-FD-002）；
- 用户数据可导出、可迁移（REQ-FD-003，P1）。

相关需求：REQ-FD-001
"""

from __future__ import annotations

from dataclasses import dataclass


class FederationError(RuntimeError):
    pass


@dataclass(frozen=True)
class NodeInfo:
    node_id: str
    kind: str  # "peer" | "hub"
    capacity: int = 1  # 相对处理能力

    def __post_init__(self) -> None:
        if self.kind not in ("peer", "hub"):
            raise FederationError("kind 必须是 peer 或 hub")
        if self.capacity <= 0:
            raise FederationError("capacity 必须为正")


class TrafficRouter:
    def __init__(self, max_hub_share: float = 0.2) -> None:
        if not 0 < max_hub_share < 1:
            raise FederationError("max_hub_share 必须在 (0,1)")
        self.max_hub_share = max_hub_share
        self.nodes: dict[str, NodeInfo] = {}
        self.served: dict[str, int] = {}

    def add(self, node: NodeInfo) -> None:
        self.nodes[node.node_id] = node
        self.served.setdefault(node.node_id, 0)

    def new_epoch(self) -> None:
        self.served = {k: 0 for k in self.nodes}

    def share(self, node_id: str) -> float:
        total = sum(self.served.values())
        return self.served.get(node_id, 0) / total if total else 0.0

    def route(self) -> str:
        """选择负载/能力比最小的节点；hub 若接单后会超出份额上限则跳过。"""
        if not self.nodes:
            raise FederationError("没有可用节点")
        total_after = sum(self.served.values()) + 1
        candidates = []
        for n in self.nodes.values():
            if n.kind == "hub" and (self.served[n.node_id] + 1) / total_after > self.max_hub_share:
                continue
            candidates.append(n)
        if not candidates:
            # 只有 hub 时无法满足上限；仍需服务，但选择份额最低的 hub
            candidates = list(self.nodes.values())
        best = min(candidates, key=lambda n: (self.served[n.node_id] / n.capacity, n.node_id))
        self.served[best.node_id] += 1
        return best.node_id
