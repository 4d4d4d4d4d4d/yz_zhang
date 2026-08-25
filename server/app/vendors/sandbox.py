"""STUB-010~033 沙箱桩实现（27 号 spec）。

> **为什么需要这些桩**：抽象层建好了但只发布退化实现，等于没预留接口——
> 换供应商那天才第一次执行到这些分支，而那正是最不能出错的时刻。
> 这里为每个预留接口补一套**形态真实**的实现，让「合规形态」的完整闭环
> 现在就能跑通并被测试钉死。
>
> **红线不变**：沙箱桩与 mock 一样属于非生产实现，`startup_check` 一视同仁地
> 拒绝。它们让路径可测，不让平台可上线。
"""
import hashlib
import hmac
import os
import uuid
from dataclasses import dataclass, field

from app.core.config import settings

from .base import VendorError, VendorResult
from .notary import NotaryReceipt
from .signature import SignatureResult

# STUB-013 失败注入：用于验证失败路径（回滚、告警、不留脏数据）。
# 这类分支比成功路径更需要提前跑过。
FAIL_MODE_ENV = "PLATFORM_SANDBOX_FAIL_MODE"


def _fail_mode() -> str:
    return os.environ.get(FAIL_MODE_ENV, "")


def _maybe_fail(operation: str) -> None:
    mode = _fail_mode()
    if mode and mode in (operation, "all"):
        raise VendorError("sandbox_injected_failure",
                          f"沙箱注入失败：{operation}", retryable=True)


# ── STUB-011 存管账簿：证明「钱不经过平台」在代码上真的走得通 ──────
@dataclass
class CustodyBook:
    """存管方账簿的沙箱模型。

    刻意与平台钱包**完全分离**：这里的余额代表持牌机构备付金账户里的钱，
    平台对它没有支配权，只能下达分账指令。
    """

    balances: dict[str, int] = field(default_factory=dict)
    entries: list[dict] = field(default_factory=list)

    def credit(self, account: str, amount: int, memo: str) -> None:
        self.balances[account] = self.balances.get(account, 0) + amount
        self.entries.append({"account": account, "amount": amount, "memo": memo})

    def debit(self, account: str, amount: int, memo: str) -> None:
        if self.balances.get(account, 0) < amount:
            raise VendorError("insufficient_custody_balance",
                              "存管子账户余额不足", retryable=False)
        self.balances[account] -= amount
        self.entries.append({"account": account, "amount": -amount, "memo": memo})

    def reset(self) -> None:
        self.balances.clear()
        self.entries.clear()


BOOK = CustodyBook()
ESCROW_ACCOUNT = "custody:escrow"   # 交易存管专户


class SandboxCustodyPayment:
    """STUB-010 存管形态的支付实现。

    与 `MockPaymentProvider` 的**根本区别**：付款进入存管子账户而非平台账户，
    平台只能通过 `split_settle` 下达分账指令。这正是 25 号 spec 要求的形态。
    """

    name = "sandbox"

    def create_charge(self, order_no: str, amount_cents: int, subject: str) -> VendorResult:
        _maybe_fail("create_charge")
        ref = f"sbx-ch-{uuid.uuid4().hex[:12]}"
        BOOK.credit(ESCROW_ACCOUNT, amount_cents, f"charge {order_no}")
        return VendorResult(ok=True, external_ref=ref, status="succeeded",
                            data={"pay_url": f"https://sandbox.custody/{order_no}",
                                  "amount_cents": amount_cents, "subject": subject})

    def query_charge(self, order_no: str) -> VendorResult:
        return VendorResult(ok=True, external_ref=f"sbx-ch-{order_no}", status="succeeded")

    def split_settle(self, order_no: str, splits: list) -> VendorResult:
        """FIN-003 分账指令：从存管专户按指令划给各收款方。"""
        _maybe_fail("split_settle")
        total = sum(int(s["amount_cents"]) for s in splits)
        BOOK.debit(ESCROW_ACCOUNT, total, f"settle {order_no}")
        for s in splits:
            BOOK.credit(f"custody:user:{s['payee']}", int(s["amount_cents"]),
                        f"{order_no} {s.get('purpose', '')}")
        return VendorResult(ok=True, external_ref=f"sbx-st-{uuid.uuid4().hex[:12]}",
                            status="succeeded", data={"total_cents": total,
                                                      "split_count": len(splits)})

    def create_payout(self, order_no: str, payee: dict, amount_cents: int) -> VendorResult:
        _maybe_fail("create_payout")
        return VendorResult(ok=True, external_ref=f"sbx-po-{uuid.uuid4().hex[:12]}",
                            status="succeeded",
                            data={"payee_kind": payee.get("kind", ""),
                                  "amount_cents": amount_cents})

    def query_payout(self, order_no: str) -> VendorResult:
        return VendorResult(ok=True, external_ref=f"sbx-po-{order_no}", status="succeeded")

    def query_balance(self, sub_account: str) -> VendorResult:
        return VendorResult(ok=True, external_ref=sub_account,
                            data={"balance_cents": BOOK.balances.get(sub_account, 0)})

    def verify_callback(self, payload: dict, signature: str) -> bool:
        from .payment import sign_callback

        return signature == sign_callback(payload)


# ── STUB-020 可靠电子签名沙箱 ────────────────────────────────────
class SandboxCaSignature:
    """模拟第三方 CA：返回签名值 + 证书 + 可信时间戳，`reliability=qualified`。

    桩的价值在于**把契约钉死**——所以 `verify` 必须真的能验，
    只返回固定值的桩没有意义（STUB-022）。
    """

    name = "sandbox-ca"
    reliability = "qualified"

    def _mac(self, signer_id: int, document_hash: str, serial: str) -> str:
        payload = f"ca:{signer_id}:{document_hash}:{serial}"
        return hmac.new(settings.JWT_SECRET.encode(), payload.encode(),
                        hashlib.sha256).hexdigest()

    def sign(self, signer_id: int, document_hash: str, meta: dict) -> SignatureResult:
        _maybe_fail("sign")
        serial = uuid.uuid4().hex[:16].upper()
        return SignatureResult(
            signature=self._mac(signer_id, document_hash, serial),
            certificate=f"SANDBOX-CA-CERT:{serial}",
            timestamp_token=f"SANDBOX-TSA:{uuid.uuid4().hex[:16]}",
            algorithm="RSA-SHA256",
            reliability=self.reliability,
            provider=self.name,
            extra={"serial": serial, **{k: v for k, v in meta.items() if k != "ip"}},
        )

    def verify(self, signer_id: int, document_hash: str, result: SignatureResult) -> bool:
        serial = (result.extra or {}).get("serial", "")
        return hmac.compare_digest(
            self._mac(signer_id, document_hash, serial), result.signature or "")


# ── STUB-021 第三方存证沙箱 ──────────────────────────────────────
class SandboxNotary:
    """模拟司法存证：返回可质证的存证编号，`backed=True`。"""

    name = "sandbox-notary"
    backed = True

    def notarize(self, chain_head: str, seq_from: int, seq_to: int) -> NotaryReceipt:
        _maybe_fail("notarize")
        return NotaryReceipt(
            receipt_no=f"SBX-NOTARY-{seq_from}-{seq_to}-{chain_head[:12]}",
            authority="沙箱存证机构（模拟司法链）",
            backed=True,
            detail=f"覆盖 seq {seq_from}~{seq_to}，链 head {chain_head[:16]}…",
        )


# ── STUB-030 eKYC 三态 ───────────────────────────────────────────
class SandboxKycProvider:
    """按证件号尾号触发三种结果，使 `manual` 转人工分支可测。

    规则（沙箱约定，写在这里而不是散在测试里）：
      尾号 0000 → failed（核验不通过）
      尾号 9999 → manual（转人工复核）
      其余      → passed
    """

    name = "sandbox"

    def verify(self, real_name: str, id_no: str, **extra) -> VendorResult:
        _maybe_fail("kyc")
        if len(id_no) not in (15, 18) or len(real_name) < 2:
            status = "failed"
        elif id_no.endswith("0000"):
            status = "failed"
        elif id_no.endswith("9999"):
            status = "manual"
        else:
            status = "passed"
        return VendorResult(ok=True, external_ref=f"sbx-kyc-{uuid.uuid4().hex[:10]}",
                            status=status)


# ── STUB-031 严格短信路径 ────────────────────────────────────────
class SandboxSmsProvider:
    """不回显验证码，走**真实通道的严格路径**。

    `mock` 的固定码让「必须先请求验证码、有效期、尝试次数上限」这段逻辑
    永远不被执行；沙箱短信就是为了覆盖它。
    """

    name = "sandbox"
    echoes_code = False

    def __init__(self) -> None:
        # 沙箱专用：把发出去的码留在内存里供测试读取（真实通道当然没有这个）
        self.sent: dict[str, str] = {}

    def send_code(self, phone: str, code: str, template: str = "verify") -> VendorResult:
        _maybe_fail("send_sms")
        self.sent[phone] = code
        return VendorResult(ok=True, external_ref=f"sbx-sms-{uuid.uuid4().hex[:10]}",
                            data={"template": template})


# ── STUB-032 内容审核三态 ────────────────────────────────────────
class SandboxModeration:
    """可配置返回，覆盖转人工分支。"""

    name = "sandbox"

    def check(self, kind: str, text: str, media_urls: list[str] | None = None) -> VendorResult:
        _maybe_fail("moderation")
        from app.modules.task.service import BANNED_WORDS

        hits = [w for w in BANNED_WORDS if w in text]
        if hits:
            status = "reject"
        elif media_urls or "待审" in text:
            status = "review"   # 有媒体内容一律转人工，与真实供应商的保守取向一致
        else:
            status = "pass"
        return VendorResult(ok=True, external_ref=f"sbx-mod-{uuid.uuid4().hex[:8]}",
                            status=status, data={"labels": hits})


# ── STUB-033 直传形态的对象存储 ──────────────────────────────────
class SandboxStorage:
    """签发直传 URL 形态：文件不经过平台，与真实对象存储一致。

    读取仍复用本地目录，因为沙箱没有真的 CDN；但 `sign_upload` 的契约
    与真实实现一致，接入时不用改调用方。
    """

    name = "sandbox"

    def __init__(self) -> None:
        from .storage import LocalStorageProvider

        self._local = LocalStorageProvider()

    def put(self, data: bytes, content_type: str) -> VendorResult:
        _maybe_fail("storage_put")
        return self._local.put(data, content_type)

    def sign_upload(self, content_type: str) -> VendorResult:
        token = uuid.uuid4().hex
        return VendorResult(ok=True, external_ref=token,
                            data={"direct_upload": True,
                                  "upload_url": f"https://sandbox.oss/put/{token}",
                                  "expires_in": 900})

    def read(self, name: str):
        return self._local.read(name)


def reset_sandbox() -> None:
    """测试辅助：清空存管账簿与失败注入。"""
    BOOK.reset()
    os.environ.pop(FAIL_MODE_ENV, None)
