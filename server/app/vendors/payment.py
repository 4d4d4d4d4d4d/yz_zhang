"""VND-010~014 支付与提现供应商。

接口按「持牌机构担保交易」的通用形态设计：下单拿支付参数 → 用户支付 →
回调/主动查询确认 → 平台入账。提现同理（发起打款 → 查询到账）。
"""
import hashlib
import hmac
import uuid
from typing import Protocol

from app.core.config import settings

from .base import VendorResult


class PaymentProvider(Protocol):
    name: str

    def create_charge(self, order_no: str, amount_cents: int, subject: str) -> VendorResult:
        """发起收款：返回支付链接/预支付参数与外部单号。"""

    def query_charge(self, order_no: str) -> VendorResult:
        """查询收款状态（回调丢失时的兜底对账手段）。"""

    def create_payout(self, order_no: str, payee: dict, amount_cents: int) -> VendorResult:
        """发起打款到收款账户。"""

    def query_payout(self, order_no: str) -> VendorResult: ...

    def verify_callback(self, payload: dict, signature: str) -> bool:
        """VND-012 回调验签：签名不通过一律拒绝。"""


class MockPaymentProvider:
    """开发/CI 缺省实现：即时成功，无需任何密钥。

    保留与真实供应商完全一致的调用序列（下单 → 确认），
    因此接真实通道时业务代码与测试都不用改。
    """

    name = "mock"

    def create_charge(self, order_no: str, amount_cents: int, subject: str) -> VendorResult:
        return VendorResult(
            ok=True,
            external_ref=f"mock-ch-{uuid.uuid4().hex[:12]}",
            status="succeeded",  # 模拟通道即时到账
            data={"pay_url": f"https://mock.pay/{order_no}", "amount_cents": amount_cents,
                  "subject": subject},
        )

    def query_charge(self, order_no: str) -> VendorResult:
        return VendorResult(ok=True, external_ref=f"mock-ch-{order_no}", status="succeeded")

    def create_payout(self, order_no: str, payee: dict, amount_cents: int) -> VendorResult:
        return VendorResult(
            ok=True,
            external_ref=f"mock-po-{uuid.uuid4().hex[:12]}",
            status="succeeded",
            data={"payee_kind": payee.get("kind", ""), "amount_cents": amount_cents},
        )

    def query_payout(self, order_no: str) -> VendorResult:
        return VendorResult(ok=True, external_ref=f"mock-po-{order_no}", status="succeeded")

    def verify_callback(self, payload: dict, signature: str) -> bool:
        return signature == sign_callback(payload)


def sign_callback(payload: dict) -> str:
    """回调签名算法（模拟通道用平台密钥；真实通道换成供应商的验签规则）。

    按 key 排序拼接后 HMAC-SHA256——与主流支付网关一致的做法，
    保证「同样的字段集合只有一个合法签名」，防止字段重排绕过。
    """
    body = "&".join(f"{k}={payload[k]}" for k in sorted(payload) if k != "sign")
    return hmac.new(settings.JWT_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
