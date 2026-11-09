"""内容对象（L1 层）。

内容以哈希寻址：content_id = sha256(规范化 payload)。作者签名保证来源不可抵赖，
`ai_generated` 为强制披露字段（REQ-CT-003）。

相关需求：REQ-CT-001, REQ-CT-002, REQ-CT-003
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import crypto

MAX_TITLE_LEN = 200
MAX_BODY_LEN = 20_000
MAX_TAGS = 10


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
        }

    @property
    def id(self) -> str:
        return crypto.content_hash(self.payload())

    def verify(self) -> bool:
        return crypto.verify(self.author, self.payload(), self.signature)

    def to_dict(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Content:
        return cls(
            author=d["author"],
            title=d["title"],
            body=d["body"],
            created_at=int(d["created_at"]),
            ai_generated=bool(d["ai_generated"]),
            media=tuple(d.get("media", ())),
            tags=tuple(d.get("tags", ())),
            signature=d["signature"],
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
) -> Content:
    unsigned = Content(
        author=identity.did,
        title=title,
        body=body,
        created_at=created_at,
        ai_generated=ai_generated,
        media=tuple(media),
        tags=tuple(t.lower() for t in tags),
    )
    signed = Content(**{**unsigned.__dict__, "signature": identity.sign(unsigned.payload())})
    validate(signed)
    return signed
