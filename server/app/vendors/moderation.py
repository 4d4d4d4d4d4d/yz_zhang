"""VND-030 内容安全审核供应商。"""
import uuid
from typing import Protocol

from .base import VendorResult


class ModerationProvider(Protocol):
    name: str

    def check(self, kind: str, text: str, media_urls: list[str] | None = None) -> VendorResult:
        """返回 status ∈ pass / review（转人工）/ reject，附命中标签。"""


class LocalModerationProvider:
    """开发/CI 缺省：复用平台内置违禁词表（现状实现，行为不变）。

    真实供应商能识别图片/视频与语义变体；本地词表只挡最直白的一类，
    因此生产自检把 moderation 列为 P0 kind（VND-042）。
    """

    name = "local"

    def check(self, kind: str, text: str, media_urls: list[str] | None = None) -> VendorResult:
        from app.modules.task.service import BANNED_WORDS

        hits = [w for w in BANNED_WORDS if w in text]
        if media_urls:
            # 本地实现看不了图/视频——明确标记为需人工复核，而不是假装通过
            return VendorResult(
                ok=True, external_ref=f"local-{uuid.uuid4().hex[:8]}",
                status="reject" if hits else "review",
                data={"labels": hits, "reason": "media_not_inspectable"},
            )
        return VendorResult(
            ok=True, external_ref=f"local-{uuid.uuid4().hex[:8]}",
            status="reject" if hits else "pass",
            data={"labels": hits},
        )
