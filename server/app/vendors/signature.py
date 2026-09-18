"""LAW-001/002 电子签名供应商（26 号 spec）。

> **先说清楚现状的法律地位**：此前的「双签」只是平台数据库里的两个布尔位
> （`signed_by_requester` / `signed_by_executor`）。这**不构成
> 《电子签名法》第十三条的「可靠电子签名」**——签名制作数据不专属签名人，
> 平台既是存储方又是裁判方，对方在诉讼中一句「不是我签的」就可能推翻。
>
> `PlatformWitnessSignature`（缺省实现）诚实地把自己标注为
> `reliability="platform_witness"`：它能证明「平台记录到这次点击，且此后
> 合同文本未被改动」，但**不能独立证明签名人身份**。
> 接第三方 CA 后才是 `reliability="qualified"`。
>
> 证据包会把这个区别**明确写出来**（LAW-013）——诚实标注证明力边界，
> 好过让人误以为全部有司法效力。
"""
import hashlib
import hmac
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import settings


@dataclass
class SignatureResult:
    signature: str
    certificate: str = ""          # 签名证书（真实 CA 才有）
    timestamp_token: str = ""      # 可信时间戳令牌（TSA 才有）
    algorithm: str = "HMAC-SHA256"
    reliability: str = "platform_witness"   # platform_witness / qualified
    provider: str = "platform"
    extra: dict = field(default_factory=dict)


class SignatureProvider(Protocol):
    name: str
    reliability: str

    def sign(self, signer_id: int, document_hash: str, meta: dict) -> SignatureResult: ...

    def verify(self, signer_id: int, document_hash: str, result: SignatureResult) -> bool: ...


class PlatformWitnessSignature:
    """缺省实现：平台见证签名。

    做的事：把「谁、在什么时刻、对哪一份文本（哈希）表示同意」用平台密钥
    做 HMAC 固定下来。文本一改哈希就对不上，**篡改自证**。
    做不到的事：证明签名制作数据专属于签名人——那需要 CA 签发的个人证书。
    """

    name = "platform"
    reliability = "platform_witness"

    def _mac(self, signer_id: int, document_hash: str, nonce: str) -> str:
        payload = f"{signer_id}:{document_hash}:{nonce}"
        return hmac.new(settings.JWT_SECRET.encode(), payload.encode(),
                        hashlib.sha256).hexdigest()

    def sign(self, signer_id: int, document_hash: str, meta: dict) -> SignatureResult:
        nonce = uuid.uuid4().hex
        return SignatureResult(
            signature=self._mac(signer_id, document_hash, nonce),
            reliability=self.reliability,
            provider=self.name,
            extra={"nonce": nonce, **{k: v for k, v in meta.items() if k != "ip"}},
        )

    def verify(self, signer_id: int, document_hash: str, result: SignatureResult) -> bool:
        nonce = (result.extra or {}).get("nonce", "")
        expected = self._mac(signer_id, document_hash, nonce)
        # 常数时间比较：签名校验不该泄露前缀匹配长度
        return hmac.compare_digest(expected, result.signature or "")


def _sandbox_ca() -> type:
    from .sandbox import SandboxCaSignature

    return SandboxCaSignature


_REGISTRY: dict[str, type] = {"platform": PlatformWitnessSignature}
_provider: SignatureProvider | None = None


def get_signature_provider() -> SignatureProvider:
    global _provider
    if _provider is None:
        name = settings.SIGNATURE_PROVIDER
        factory = _sandbox_ca() if name == "sandbox-ca" else \
            _REGISTRY.get(name, PlatformWitnessSignature)
        _provider = factory()
    return _provider


def set_signature_provider(provider: SignatureProvider | None) -> None:
    global _provider
    _provider = provider


def document_hash(text: str) -> str:
    """LAW-002 签署时刻的**合同全文**哈希。

    必须是签署那一刻的全文——事后改条款则哈希对不上，篡改无法隐藏。
    """
    return hashlib.sha256(text.encode()).hexdigest()
