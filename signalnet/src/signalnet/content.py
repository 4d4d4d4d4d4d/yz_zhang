"""内容对象（L1 层）。

内容以哈希寻址：content_id = sha256(规范化 payload)。作者签名保证来源不可抵赖，
`ai_generated` 为强制披露字段（REQ-CT-003）。

扩展字段：
- derived_from：衍生声明（REQ-OR-003）
- revises：作者对自己旧内容的修订（REQ-CT-004）
- timeliness：timely（时效型）/ evergreen（常青型）（REQ-EV-002）
- category：news / tutorial / entertainment / art / general（REQ-PS-011）
- media_fp：媒体关键帧感知哈希（hex），由 L3 媒体服务计算并随内容签名（REQ-OR-008）
- signing_key：密钥轮换后的签名公钥；为空表示 DID 初始公钥（REQ-ID-003）

相关需求：REQ-CT-001 ~ REQ-CT-004, REQ-OR-003, REQ-OR-008, REQ-EV-002, REQ-PS-011
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from . import crypto

MAX_TITLE_LEN = 200
MAX_BODY_LEN = 20_000
MAX_TAGS = 10
MAX_DERIVED = 10
TIMELINESS = ("evergreen", "timely")
CATEGORIES = ("general", "news", "tutorial", "entertainment", "art")


class ContentError(ValueError):
    pass


@dataclass(frozen=True)
class Content:
    author: str
    title: str
    body: str
    created_at: int
    ai_generated: bool
    media: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    signature: str = ""
    derived_from: tuple[str, ...] = field(default_factory=tuple)
    revises: str = ""
    timeliness: str = "evergreen"
    category: str = "general"
    media_fp: tuple[str, ...] = field(default_factory=tuple)
    signing_key: str = ""

    def payload(self) -> dict[str, Any]:
        return {
            "type": "content/v1",
            "author": self.author,
            "title": self.title,
            "body": self.body,
            "created_at": self.created_at,
            "ai_generated": self.ai_generated,
            "media": list(self.media),
            "tags": list(self.tags),
            "derived_from": list(self.derived_from),
            "revises": self.revises,
            "timeliness": self.timeliness,
            "category": self.category,
            "media_fp": list(self.media_fp),
            "signing_key": self.signing_key,
        }

    @property
    def id(self) -> str:
        return crypto.content_hash(self.payload())

    @property
    def key(self) -> str:
        return self.signing_key or crypto.key_of_did(self.author)

    def verify(self) -> bool:
        return crypto.verify_key(self.key, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Content:
        return cls(
            author=d["author"],
            title=d["title"],
            body=d["body"],
            created_at=int(d["created_at"]),
            ai_generated=d["ai_generated"],
            media=tuple(d.get("media", ())),
            tags=tuple(d.get("tags", ())),
            signature=d["signature"],
            derived_from=tuple(d.get("derived_from", ())),
            revises=d.get("revises", ""),
            timeliness=d.get("timeliness", "evergreen"),
            category=d.get("category", "general"),
            media_fp=tuple(d.get("media_fp", ())),
            signing_key=d.get("signing_key", ""),
        )


def validate(c: Content) -> None:
    if not crypto.is_valid_did(c.author):
        raise ContentError("author 不是合法 DID")
    if not c.title.strip() or len(c.title) > MAX_TITLE_LEN:
        raise ContentError("title 为空或过长")
    if len(c.body) > MAX_BODY_LEN:
        raise ContentError("body 过长")
    if len(c.tags) > MAX_TAGS:
        raise ContentError("tags 过多")
    if not isinstance(c.ai_generated, bool):
        raise ContentError("ai_generated 必须显式声明为 bool")
    if c.timeliness not in TIMELINESS:
        raise ContentError(f"timeliness 必须是 {TIMELINESS}")
    if c.category not in CATEGORIES:
        raise ContentError(f"category 必须是 {CATEGORIES}")
    if len(c.derived_from) > MAX_DERIVED or len(set(c.derived_from)) != len(c.derived_from):
        raise ContentError("derived_from 过多或重复")
    if c.revises and c.revises in c.derived_from:
        raise ContentError("修订不能同时声明为衍生")
    for fp in c.media_fp:
        if len(fp) != 16:
            raise ContentError("media_fp 必须是 64 位 hex")
        int(fp, 16)
    if not c.verify():
        raise ContentError("签名无效")


def create_content(
    identity: crypto.Identity,
    title: str,
    body: str,
    *,
    created_at: int,
    ai_generated: bool,
    media: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    derived_from: tuple[str, ...] = (),
    revises: str = "",
    timeliness: str = "evergreen",
    category: str = "general",
    media_fp: tuple[str, ...] = (),
    as_did: str = "",
) -> Content:
    """as_did：密钥轮换后，用新密钥代表原 DID 发布。"""
    unsigned = Content(
        author=as_did or identity.did,
        title=title,
        body=body,
        created_at=created_at,
        ai_generated=ai_generated,
        media=tuple(media),
        tags=tuple(t.lower() for t in tags),
        derived_from=tuple(derived_from),
        revises=revises,
        timeliness=timeliness,
        category=category,
        media_fp=tuple(media_fp),
        signing_key=identity.public_key_hex if as_did else "",
    )
    signed = replace(unsigned, signature=identity.sign(unsigned.payload()))
    validate(signed)
    return signed
