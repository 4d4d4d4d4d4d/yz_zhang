"""随机陪审（L2 层）：确定性加权抽签 + commit-reveal 校验 + 波次权重。

- 抽签种子 = sha256(content_id | 轮次 | 开轮时的日志 head)：开轮前无人能预知结果，
  开轮后任何节点都能复算（REQ-CS-002）。
- 加权无放回抽样（Efraimidis-Spirakis）：key = -ln(u) / w，取 key 最小的 k 个。
- 发现者奖励：首轮陪审在策展分成中权重 ×3、第二轮 ×2、其后 ×1（REQ-CS-005）。

相关需求：REQ-CS-002, REQ-CS-005
"""

from __future__ import annotations

import math

from . import crypto
from .attestation import Attestation, Commit, commitment


def seed_for(content_id: str, round_index: int, head: str) -> str:
    return crypto.sha256_hex(f"{content_id}|{round_index}|{head}".encode())


def _uniform(seed: str, did: str) -> float:
    h = int(crypto.sha256_hex(f"{seed}|{did}".encode())[:16], 16)
    return (h + 1) / (2**64 + 1)  # ∈ (0,1)


def draw(candidates: dict[str, float], k: int, seed: str) -> tuple[str, ...]:
    """candidates: {did: 权重>0}。返回按抽中顺序排列的 k 个 DID（确定性）。"""
    keyed = sorted(
        (-math.log(_uniform(seed, did)) / w, did) for did, w in candidates.items() if w > 0
    )
    return tuple(did for _, did in keyed[:k])


def wave_weight(round_index: int, weights: tuple[int, ...] = (3, 2, 1)) -> int:
    if round_index < len(weights):
        return weights[round_index]
    return weights[-1]


def reveal_matches(commit: Commit, a: Attestation, salt: str) -> bool:
    return (
        commit.reviewer == a.reviewer
        and commit.content_id == a.content_id
        and commit.round == a.round
        and commit.commitment == commitment(a, salt)
    )
