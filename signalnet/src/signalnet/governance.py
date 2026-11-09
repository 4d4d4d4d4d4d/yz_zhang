"""参数治理（L2 层）：参数变更必须公示、投票，并在公示期满后才生效（REQ-GV-001）。

只有登记在 GOVERNABLE 中的参数可以被治理，且每个参数有硬边界——
例如创作者分成不得低于 50%、单 hub 份额不得高于 50%，治理也无法突破愿景约束。

相关需求：REQ-GV-001
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 参数名 -> (类型, 下限, 上限)
GOVERNABLE: dict[str, tuple[type, float, float]] = {
    "explore_ratio": (float, 0.0, 0.3),
    "revival_ratio": (float, 0.0, 0.2),
    "promote_threshold": (float, 0.5, 0.95),
    "max_hub_share": (float, 0.05, 0.5),
    "creator_bps": (int, 5000, 9000),
    "curators_bps": (int, 0, 3000),
    "node_bps": (int, 0, 3000),
    "commons_bps": (int, 0, 3000),
}


class GovernanceError(ValueError):
    pass


def validate_param(param: str, value: Any) -> Any:
    if param not in GOVERNABLE:
        raise GovernanceError(f"参数 {param} 不可治理")
    typ, lo, hi = GOVERNABLE[param]
    if typ is int and (not isinstance(value, int) or isinstance(value, bool)):
        raise GovernanceError(f"{param} 必须是整数")
    if typ is float and not isinstance(value, int | float):
        raise GovernanceError(f"{param} 必须是数字")
    if not lo <= value <= hi:
        raise GovernanceError(f"{param} 必须在 [{lo}, {hi}]")
    return typ(value)


@dataclass
class Proposal:
    proposal_id: str
    proposer: str
    param: str
    value: Any
    created_at: int
    effective_at: int
    votes: dict[str, tuple[bool, float]] = field(default_factory=dict)
    resolved: bool = False
    passed: bool = False


def passes(p: Proposal) -> bool:
    yes = sum(w for v, w in p.votes.values() if v)
    no = sum(w for v, w in p.votes.values() if not v)
    return yes > no and yes > 0
