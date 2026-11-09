"""质量证明（Attestation，L1 层）。

评审者对内容给出三维评分并“质押声誉”（不是代币）。签名保证评审不可伪造。

相关需求：REQ-AT-001, REQ-AT-002
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import crypto

# 三维评分权重：准确性、质量、有用性
SCORE_WEIGHTS = {"accuracy": 0.4, "quality": 0.4, "usefulness": 0.2}


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

    def payload(self) -> dict[str, Any]:
        return {
            "type": "attestation/v1",
            "reviewer": self.reviewer,
            "content_id": self.content_id,
            "accuracy": self.accuracy,
            "quality": self.quality,
            "usefulness": self.usefulness,
            "stake": self.stake,
            "created_at": self.created_at,
        }

    @property
    def id(self) -> str:
        return crypto.content_hash(self.payload())

    @property
    def score(self) -> float:
        return (
            SCORE_WEIGHTS["accuracy"] * self.accuracy
            + SCORE_WEIGHTS["quality"] * self.quality
            + SCORE_WEIGHTS["usefulness"] * self.usefulness
        )

    def verify(self) -> bool:
        return crypto.verify(self.reviewer, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attestation:
        return cls(
            reviewer=d["reviewer"],
            content_id=d["content_id"],
            accuracy=float(d["accuracy"]),
            quality=float(d["quality"]),
            usefulness=float(d["usefulness"]),
            stake=int(d["stake"]),
            created_at=int(d["created_at"]),
            signature=d["signature"],
        )


def validate(a: Attestation) -> None:
    for name in ("accuracy", "quality", "usefulness"):
        v = getattr(a, name)
        if not (0.0 <= v <= 1.0):
            raise AttestationError(f"{name} 必须在 [0,1] 区间")
    if a.stake <= 0:
        raise AttestationError("stake 必须为正整数")
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
) -> Attestation:
    unsigned = Attestation(
        reviewer=identity.did,
        content_id=content_id,
        accuracy=float(accuracy),
        quality=float(quality),
        usefulness=float(usefulness),
        stake=int(stake),
        created_at=created_at,
    )
    signed = Attestation(**{**unsigned.__dict__, "signature": identity.sign(unsigned.payload())})
    validate(signed)
    return signed
