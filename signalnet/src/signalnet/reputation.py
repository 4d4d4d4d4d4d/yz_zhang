"""PoS 引擎：Proof of Signal（信号证明 / 声誉质押）。L2 层。

核心思想：
- 声誉（reputation）是**不可转让、不可买卖**的积分，绑定 DID，不是代币（ADR-0001）。
- 评审者质押声誉为内容质量背书；按质押权重求**加权中位数**得出共识分。
- 评审与共识一致 → 获得声誉奖励；偏离共识 → 被罚没（slash）。
- 权重 = sqrt(stake)，并对单个评审者的权重占比设上限，抑制“鲸鱼”和合谋。
- 作者声誉随其内容的共识质量涨跌。

相关需求：REQ-PS-001 ~ REQ-PS-011
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .attestation import SCORE_WEIGHTS, Attestation


class ReputationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PoSParams:
    initial_rep: int = 100
    min_rep_to_attest: int = 10
    max_stake_fraction: float = 0.2  # 单次质押不得超过可用声誉的比例
    tolerance: float = 0.15  # |评分-共识| <= tolerance 视为一致
    reward_rate: float = 0.10  # 一致者奖励 = stake * reward_rate
    slash_rate: float = 0.20  # 偏离者罚没 = stake * slash_rate
    author_rate: int = 20  # 作者声誉变化 = (consensus-0.5)*2*author_rate*confidence
    max_weight_share: float = 0.34  # 单个评审者权重占比上限（评审人数>=3 时生效）
    confidence_k: float = 10.0  # 置信度饱和常数


@dataclass(frozen=True)
class Settlement:
    content_id: str
    consensus: float
    confidence: float
    rewards: dict[str, int] = field(default_factory=dict)
    slashes: dict[str, int] = field(default_factory=dict)
    author: str = ""
    author_delta: int = 0
    aligned: tuple[str, ...] = ()  # 与共识一致的评审者（用于广告收益里的策展人分成）
    evidence: float = 0.0  # 评审权重和 E（排序用于贝叶斯收缩，REQ-CS-004）
    agreement: float = 1.0  # 一致度 = 1 - 2×加权离散度，∈[0,1]
    bridged: bool = False  # 跨群体一致（REQ-PS-008）
    cluster_medians: dict[str, float] = field(default_factory=dict)


def weighted_median(values: list[tuple[float, float]]) -> float:
    """values: [(score, weight)]。确定性：同分按 score 升序。"""
    if not values:
        raise ValueError("empty")
    items = sorted(values)
    total = sum(w for _, w in items)
    acc = 0.0
    for score, w in items:
        acc += w
        if acc >= total / 2:
            return score
    return items[-1][0]


def cap_shares(w: list[float], max_share: float) -> list[float]:
    """单者占比上限（精确水位解）。

    设被封顶集合为 C（大小 k），其余权重和为 R，封顶值 x 满足 x = s * (k*x + R)，
    即 x = s*R / (1 - s*k)。从大到小尝试 k，找到使 C 内都 >= x、C 外都 <= x 的解。
    人数 < 3 或 n*s < 1（上限不可满足）时不封顶。
    """
    w = list(w)
    n = len(w)
    if n < 3 or n * max_share < 1 or max(w) <= max_share * sum(w):
        return w
    order = sorted(range(n), key=lambda i: -w[i])
    for k in range(1, n):
        if max_share * k >= 1:
            break
        rest = sum(w[i] for i in order[k:])
        x = max_share * rest / (1 - max_share * k)
        if w[order[k - 1]] >= x >= w[order[k]]:
            out = list(w)
            for i in order[:k]:
                out[i] = x
            return out
    return w


def capped_weights(stakes: list[int], max_share: float) -> list[float]:
    """sqrt 权重 + 单者占比上限。"""
    return cap_shares([math.sqrt(s) for s in stakes], max_share)


class ReputationBook:
    def __init__(self, params: PoSParams | None = None) -> None:
        self.params = params or PoSParams()
        self._balance: dict[str, int] = {}
        self._locked: dict[str, int] = {}
        self.fund = 0  # 新人扶持池（声誉衰减注入，REQ-PS-010）

    # ---- 账户 ----
    def register(self, did: str, bonus: int = 0) -> int:
        """注册并返回实际发放的新人扶持声誉。"""
        if did in self._balance:
            return 0
        grant = min(max(0, bonus), self.fund)
        self.fund -= grant
        self._balance[did] = self.params.initial_rep + grant
        self._locked[did] = 0
        return grant

    def is_registered(self, did: str) -> bool:
        return did in self._balance

    def balance(self, did: str) -> int:
        return self._balance.get(did, 0)

    def available(self, did: str) -> int:
        return self.balance(did) - self._locked.get(did, 0)

    def locked(self, did: str) -> int:
        return self._locked.get(did, 0)

    def snapshot(self) -> dict[str, int]:
        return dict(sorted(self._balance.items()))

    # ---- 质押与直接奖惩 ----
    def lock(self, did: str, amount: int, *, check_min: bool = True) -> None:
        if did not in self._balance:
            raise ReputationError("未注册的身份")
        if check_min and self.balance(did) < self.params.min_rep_to_attest:
            raise ReputationError("声誉不足，无法评审")
        if amount <= 0:
            raise ReputationError("质押必须为正")
        limit = max(1, int(self.available(did) * self.params.max_stake_fraction))
        if amount > limit:
            raise ReputationError(f"质押超过上限 {limit}")
        self._locked[did] += amount

    def unlock(self, did: str, amount: int) -> None:
        if did in self._locked:
            self._locked[did] = max(0, self._locked[did] - amount)

    def slash(self, did: str, amount: int) -> int:
        """罚没，返回实际罚没数（声誉不为负）。"""
        if did not in self._balance or amount <= 0:
            return 0
        actual = min(amount, self._balance[did])
        self._balance[did] -= actual
        self._locked[did] = min(self._locked[did], self._balance[did])
        return actual

    def reward(self, did: str, amount: int) -> None:
        if amount > 0:
            self.register(did)
            self._balance[did] += amount

    def decay(self, dids: list[str], rate: float) -> int:
        """对不活跃账户超出初始值的部分按比例衰减，注入新人扶持池（REQ-PS-010）。"""
        moved = 0
        for did in sorted(dids):
            excess = self.balance(did) - self.params.initial_rep
            amt = int(excess * rate) if excess > 0 else 0
            if amt > 0:
                moved += self.slash(did, amt)
        self.fund += moved
        return moved

    # ---- 结算 ----
    def compute(
        self,
        attestations: list[Attestation],
        author: str,
        *,
        score_weights: dict[str, float] | None = None,
        multipliers: dict[str, float] | None = None,
        clusters: dict[str, str] | None = None,
        reward_for: set[str] | None = None,
    ) -> Settlement:
        """纯函数：只依据签名评审计算结算结果，不修改状态（任意节点可复算）。

        - score_weights：分品类权重（REQ-PS-011）
        - multipliers：评审者权重乘数（女巫抵抗渐进解锁，REQ-PS-009）
        - clusters：评审者所属群体（桥接共识，REQ-PS-008）
        - reward_for：本轮参与奖惩的评审 ID 集合；共识使用全部评审（波次结算，REQ-CS-003）
        """
        if not attestations:
            raise ReputationError("没有评审")
        cid = attestations[0].content_id
        if any(a.content_id != cid for a in attestations):
            raise ReputationError("评审不属于同一内容")
        # 作者不得评审自己的内容（REQ-PS-006）
        atts = sorted(
            (a for a in attestations if a.reviewer != author), key=lambda a: (a.reviewer, a.id)
        )
        if not atts:
            raise ReputationError("只有作者本人评审")
        weights_def = score_weights or SCORE_WEIGHTS
        scores = [a.score_with(weights_def) for a in atts]
        mult = multipliers or {}
        raw = [math.sqrt(a.stake) * mult.get(a.reviewer, 1.0) for a in atts]
        weights = cap_shares(raw, self.params.max_weight_share)
        consensus = weighted_median(list(zip(scores, weights, strict=True)))
        total_w = sum(weights)
        dispersion = (
            sum(w * abs(sc - consensus) for sc, w in zip(scores, weights, strict=True)) / total_w
        )
        volume = 1.0 - math.exp(-total_w / self.params.confidence_k)
        confidence = max(0.0, min(1.0, volume * (1.0 - 2.0 * dispersion)))

        # 桥接共识：多个群体各自的中位数彼此接近才算 bridged
        bridged = False
        cluster_medians: dict[str, float] = {}
        if clusters is not None:
            groups: dict[str, list[tuple[float, float]]] = {}
            for a, sc, w in zip(atts, scores, weights, strict=True):
                groups.setdefault(clusters.get(a.reviewer, a.reviewer), []).append((sc, w))
            cluster_medians = {k: round(weighted_median(v), 6) for k, v in sorted(groups.items())}
            meds = list(cluster_medians.values())
            bridged = len(meds) >= 2 and max(meds) - min(meds) <= 2 * self.params.tolerance
            if not bridged:
                confidence *= 0.5

        rewards: dict[str, int] = {}
        slashes: dict[str, int] = {}
        aligned: list[str] = []
        for a, sc in zip(atts, scores, strict=True):
            if abs(sc - consensus) <= self.params.tolerance:
                aligned.append(a.reviewer)
            if reward_for is not None and a.id not in reward_for:
                continue
            if abs(sc - consensus) <= self.params.tolerance:
                rewards[a.reviewer] = rewards.get(a.reviewer, 0) + int(
                    a.stake * self.params.reward_rate
                )
            else:
                slashes[a.reviewer] = slashes.get(a.reviewer, 0) + max(
                    1, int(a.stake * self.params.slash_rate)
                )
        author_delta = round((consensus - 0.5) * 2 * self.params.author_rate * confidence)
        return Settlement(
            content_id=cid,
            consensus=round(consensus, 6),
            confidence=round(confidence, 6),
            rewards=rewards,
            slashes=slashes,
            author=author,
            author_delta=author_delta,
            aligned=tuple(sorted(set(aligned))),
            evidence=round(total_w, 6),
            agreement=round(max(0.0, 1.0 - 2.0 * dispersion), 6),
            bridged=bridged,
            cluster_medians=cluster_medians,
        )

    def apply(self, s: Settlement, attestations: list[Attestation]) -> None:
        for a in attestations:
            if a.reviewer in self._locked:
                self._locked[a.reviewer] = max(0, self._locked[a.reviewer] - a.stake)
        for did, amt in s.rewards.items():
            self._balance[did] = self.balance(did) + amt
        for did, amt in s.slashes.items():
            self.slash(did, amt)
        if s.author:
            self.register(s.author)
            self._balance[s.author] = max(0, self.balance(s.author) + s.author_delta)
