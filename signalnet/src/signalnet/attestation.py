"""质量证明（Attestation）与承诺（Commit），L1 层。

评审者对内容给出评分并“质押声誉”（不是代币）。签名保证评审不可伪造。

- 四维评分：准确性、质量、有用性、原创性（信息增量，可缺省）（REQ-OR-002）
- 分类投票 klass：original / derivative / follower / copy（REQ-MT-001）
- 时效投票 timely：确认作者的时效申报（REQ-EV-002）
- round：评审所属轮次（波次放量 / 复审，REQ-CS-003）
- commit-reveal：先提交 sha256(payload + salt)，揭示期再公开评审（REQ-CS-005）

相关需求：REQ-AT-001, REQ-AT-002, REQ-OR-002, REQ-MT-001, REQ-CS-005, REQ-PS-011
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from . import crypto

DIMENSIONS = ("accuracy", "quality", "usefulness", "originality")
CLASSES = ("copy", "derivative", "follower", "original")  # 判定顺序（REQ-MT-001）

# 分品类评分权重（REQ-PS-011），每行和为 1
CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "general": {"accuracy": 0.3, "quality": 0.3, "usefulness": 0.2, "originality": 0.2},
    "news": {"accuracy": 0.45, "quality": 0.2, "usefulness": 0.2, "originality": 0.15},
    "tutorial": {"accuracy": 0.3, "quality": 0.2, "usefulness": 0.35, "originality": 0.15},
    "entertainment": {"accuracy": 0.1, "quality": 0.4, "usefulness": 0.2, "originality": 0.3},
    "art": {"accuracy": 0.05, "quality": 0.45, "usefulness": 0.1, "originality": 0.4},
}
SCORE_WEIGHTS = CATEGORY_WEIGHTS["general"]


class AttestationError(ValueError):
    pass


@dataclass(frozen=True)
class Attestation:
    reviewer: str
    content_id: str
    accuracy: float
    quality: float
    usefulness: float
    stake: int
    created_at: int
    signature: str = ""
    originality: float | None = None
    klass: str = ""
    timely: bool | None = None
    round: int = 0
    signing_key: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "attestation/v1",
            "reviewer": self.reviewer,
            "content_id": self.content_id,
            "accuracy": self.accuracy,
            "quality": self.quality,
            "usefulness": self.usefulness,
            "originality": self.originality,
            "klass": self.klass,
            "timely": self.timely,
            "round": self.round,
            "stake": self.stake,
            "created_at": self.created_at,
            "signing_key": self.signing_key,
        }

    @property
    def id(self) -> str:
        return crypto.content_hash(self.payload())

    @property
    def key(self) -> str:
        return self.signing_key or crypto.key_of_did(self.reviewer)

    def score_with(self, weights: dict[str, float]) -> float:
        """加权综合分；原创性缺省时按其余维度重新归一化。"""
        total = 0.0
        wsum = 0.0
        for dim in DIMENSIONS:
            v = getattr(self, dim)
            if v is None:
                continue
            total += weights[dim] * v
            wsum += weights[dim]
        return total / wsum

    @property
    def score(self) -> float:
        return self.score_with(SCORE_WEIGHTS)

    def verify(self) -> bool:
        return crypto.verify_key(self.key, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attestation:
        orig = d.get("originality")
        return cls(
            reviewer=d["reviewer"],
            content_id=d["content_id"],
            accuracy=float(d["accuracy"]),
            quality=float(d["quality"]),
            usefulness=float(d["usefulness"]),
            stake=int(d["stake"]),
            created_at=int(d["created_at"]),
            signature=d["signature"],
            originality=None if orig is None else float(orig),
            klass=d.get("klass", ""),
            timely=d.get("timely"),
            round=int(d.get("round", 0)),
            signing_key=d.get("signing_key", ""),
        )


def validate(a: Attestation) -> None:
    for name in DIMENSIONS:
        v = getattr(a, name)
        if v is None and name == "originality":
            continue
        if v is None or not (0.0 <= v <= 1.0):
            raise AttestationError(f"{name} 必须在 [0,1] 区间")
    if a.stake <= 0:
        raise AttestationError("stake 必须为正整数")
    if a.klass and a.klass not in CLASSES:
        raise AttestationError(f"klass 必须是 {CLASSES}")
    if a.round < 0:
        raise AttestationError("round 不能为负")
    if not a.verify():
        raise AttestationError("签名无效")


def create_attestation(
    identity: crypto.Identity,
    content_id: str,
    *,
    accuracy: float,
    quality: float,
    usefulness: float,
    stake: int,
    created_at: int,
    originality: float | None = None,
    klass: str = "",
    timely: bool | None = None,
    round: int = 0,
    as_did: str = "",
) -> Attestation:
    unsigned = Attestation(
        reviewer=as_did or identity.did,
        content_id=content_id,
        accuracy=float(accuracy),
        quality=float(quality),
        usefulness=float(usefulness),
        stake=int(stake),
        created_at=created_at,
        originality=None if originality is None else float(originality),
        klass=klass,
        timely=timely,
        round=round,
        signing_key=identity.public_key_hex if as_did else "",
    )
    signed = replace(unsigned, signature=identity.sign(unsigned.payload()))
    validate(signed)
    return signed


# ---------------- commit-reveal（REQ-CS-005） ----------------
def commitment(a: Attestation, salt: str) -> str:
    return crypto.sha256_hex(crypto.canonical(a.to_dict()) + salt.encode("utf-8"))


@dataclass(frozen=True)
class Commit:
    reviewer: str
    content_id: str
    round: int
    commitment: str
    signing_key: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "commit/v1",
            "reviewer": self.reviewer,
            "content_id": self.content_id,
            "round": self.round,
            "commitment": self.commitment,
            "signing_key": self.signing_key,
        }

    @property
    def key(self) -> str:
        return self.signing_key or crypto.key_of_did(self.reviewer)

    def verify(self) -> bool:
        return crypto.verify_key(self.key, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Commit:
        return cls(
            d["reviewer"],
            d["content_id"],
            int(d["round"]),
            d["commitment"],
            d.get("signing_key", ""),
            d["signature"],
        )


def create_commit(
    identity: crypto.Identity, a: Attestation, salt: str, *, as_did: str = ""
) -> Commit:
    unsigned = Commit(
        as_did or identity.did,
        a.content_id,
        a.round,
        commitment(a, salt),
        identity.public_key_hex if as_did else "",
    )
    c = replace(unsigned, signature=identity.sign(unsigned.payload()))
    if not c.verify():
        raise AttestationError("commit 签名无效")
    return c
