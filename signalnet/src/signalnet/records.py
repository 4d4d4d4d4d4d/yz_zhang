"""通用签名记录（L1 层）：关注、密钥轮换/恢复、读者信号、曝光回执、申诉投票、治理投票等。

每条记录 = (kind, signer DID, body, signing_key, signature)。signing_key 为空表示使用 DID
内嵌的初始公钥；密钥轮换后由节点校验 signing_key 是否为该 DID 当前有效的公钥（REQ-ID-003）。

相关需求：REQ-ID-003, REQ-CS-007, REQ-AD-006, REQ-OR-004, REQ-GV-001, REQ-FD-003
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import crypto

KINDS = {
    "follow",  # body: {followee}
    "unfollow",  # body: {followee}
    "rotate_key",  # body: {new_key, seq}
    "guardians",  # body: {guardians: [did], threshold}
    "recover_approve",  # signer=守护人, body: {did, new_key, seq}
    "reader_signal",  # body: {content_id, completed, saved, worth, ts}
    "view_receipt",  # body: {campaign_id, content_id, node_id, dwell_ms, ts}
    "dispute_vote",  # body: {dispute_id, uphold}
    "gov_propose",  # body: {param, value, ts}
    "gov_vote",  # body: {proposal_id, yes}
    "invite",  # body: {invitee}
    "dispute_open",  # body: {kind: appeal|report, target, original, stake}
    "withdraw",  # body: {amount}
}


class RecordError(ValueError):
    pass


@dataclass(frozen=True)
class Record:
    kind: str
    signer: str
    body: dict[str, Any] = field(default_factory=dict)
    signing_key: str = ""
    signature: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "record/v1",
            "kind": self.kind,
            "signer": self.signer,
            "body": self.body,
            "signing_key": self.signing_key,
        }

    @property
    def id(self) -> str:
        return crypto.content_hash(self.payload())

    @property
    def key(self) -> str:
        return self.signing_key or crypto.key_of_did(self.signer)

    def verify(self) -> bool:
        return crypto.verify_key(self.key, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Record:
        return cls(
            d["kind"], d["signer"], dict(d["body"]), d.get("signing_key", ""), d["signature"]
        )


def validate(r: Record) -> None:
    if r.kind not in KINDS:
        raise RecordError(f"未知记录类型 {r.kind}")
    if not crypto.is_valid_did(r.signer):
        raise RecordError("signer 不是合法 DID")
    if not r.verify():
        raise RecordError("签名无效")


def sign_record(
    identity: crypto.Identity, kind: str, body: dict[str, Any], *, as_did: str = ""
) -> Record:
    """as_did：密钥轮换后，用新密钥代表原 DID 签名。"""
    signer = as_did or identity.did
    key = identity.public_key_hex if as_did else ""
    unsigned = Record(kind, signer, dict(body), key)
    r = Record(kind, signer, dict(body), key, identity.sign(unsigned.payload()))
    validate(r)
    return r
