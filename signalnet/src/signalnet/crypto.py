"""身份与签名原语（L0 层）。

- 身份是自证明的：DID = ``did:sn:<ed25519 公钥 hex>``，无需中心化注册。
- 所有对象使用规范化 JSON（排序键、无空白）后再哈希/签名，保证任意节点可复现。

相关需求：REQ-ID-001, REQ-ID-002, REQ-ID-003
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

DID_PREFIX = "did:sn:"


def canonical(obj: Any) -> bytes:
    """规范化 JSON 编码，跨节点字节级一致。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    return sha256_hex(canonical(obj))


@dataclass(frozen=True)
class Identity:
    """持有私钥的本地身份。私钥永不离开本地。"""

    _key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> Identity:
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_seed(cls, seed: bytes) -> Identity:
        """确定性生成（仅用于测试/仿真）。"""
        return cls(Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest()))

    @property
    def public_key_hex(self) -> str:
        raw = self._key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return raw.hex()

    @property
    def did(self) -> str:
        return DID_PREFIX + self.public_key_hex

    def sign(self, payload: Any) -> str:
        return self._key.sign(canonical(payload)).hex()


def is_valid_did(did: str) -> bool:
    if not did.startswith(DID_PREFIX):
        return False
    hex_part = did[len(DID_PREFIX) :]
    if len(hex_part) != 64:
        return False
    try:
        bytes.fromhex(hex_part)
    except ValueError:
        return False
    return True


def key_of_did(did: str) -> str:
    """DID 内嵌的初始公钥（hex）。"""
    return did[len(DID_PREFIX) :]


def is_valid_key(key_hex: str) -> bool:
    return is_valid_did(DID_PREFIX + key_hex)


def verify_key(key_hex: str, payload: Any, signature_hex: str) -> bool:
    """用指定公钥校验签名（密钥轮换后使用，REQ-ID-003）。"""
    if not is_valid_key(key_hex):
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(key_hex))
        pub.verify(bytes.fromhex(signature_hex), canonical(payload))
    except (InvalidSignature, ValueError):
        return False
    return True


def verify(did: str, payload: Any, signature_hex: str) -> bool:
    """用 DID 中内嵌的公钥校验签名。任何异常都视为校验失败。"""
    if not is_valid_did(did):
        return False
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(did[len(DID_PREFIX) :]))
        pub.verify(bytes.fromhex(signature_hex), canonical(payload))
    except (InvalidSignature, ValueError):
        return False
    return True
