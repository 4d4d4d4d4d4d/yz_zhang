"""LAW-010/011 第三方存证供应商（26 号 spec）。

> 现有的 SHA256 哈希链（`anchor` 模块）能自证「我这份数据前后一致」，
> 但**链是平台自己算的**——自己给自己作证，司法采信度有限。
>
> `LocalNotary`（缺省）诚实地返回 `backed=False`：它只把 head 记录下来，
> 没有任何外部背书。接第三方存证机构 / 司法链 / 公证处后才是 `backed=True`，
> 届时 `receipt_no` 是可以拿去质证的存证编号。
"""
from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


@dataclass
class NotaryReceipt:
    receipt_no: str
    authority: str
    backed: bool = False       # 是否有第三方背书
    detail: str = ""


class NotaryProvider(Protocol):
    name: str
    backed: bool

    def notarize(self, chain_head: str, seq_from: int, seq_to: int) -> NotaryReceipt: ...


class LocalNotary:
    """缺省实现：只记录，不背书。**不要把它当作司法存证。**"""

    name = "local"
    backed = False

    def notarize(self, chain_head: str, seq_from: int, seq_to: int) -> NotaryReceipt:
        return NotaryReceipt(
            receipt_no=f"local-{seq_from}-{seq_to}-{chain_head[:16]}",
            authority="platform-self",
            backed=False,
            detail="平台自算哈希链，无第三方背书，司法采信度有限",
        )


_REGISTRY: dict[str, type] = {"local": LocalNotary}
_provider: NotaryProvider | None = None


def get_notary() -> NotaryProvider:
    global _provider
    if _provider is None:
        factory = _REGISTRY.get(settings.NOTARY_PROVIDER, LocalNotary)
        _provider = factory()
    return _provider


def set_notary(provider: NotaryProvider | None) -> None:
    global _provider
    _provider = provider
