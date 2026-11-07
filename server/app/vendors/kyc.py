"""VND-022/023 实名核验供应商。"""
import hashlib
import hmac
import uuid
from typing import Protocol

from app.core.config import settings

from .base import VendorResult


class KycProvider(Protocol):
    name: str

    def verify(self, real_name: str, id_no: str, **extra) -> VendorResult:
        """返回 status ∈ passed / failed / manual（转人工）。"""


class MockKycProvider:
    """开发/CI 缺省：格式合法即通过（保持既有「提交即通过」的测试行为）。"""

    name = "mock"

    def verify(self, real_name: str, id_no: str, **extra) -> VendorResult:
        ok = len(id_no) in (15, 18) and len(real_name) >= 2
        return VendorResult(
            ok=True,
            external_ref=f"mock-kyc-{uuid.uuid4().hex[:10]}",
            status="passed" if ok else "failed",
        )


def id_digest(id_no: str) -> str:
    """VND-023 证件号不落明文：只存不可逆摘要，用于查重与风控关联。"""
    return hmac.new(settings.JWT_SECRET.encode(), id_no.encode(), hashlib.sha256).hexdigest()


def id_mask(id_no: str) -> str:
    """展示用掩码串（前 3 后 4）。"""
    if len(id_no) < 8:
        return "****"
    return f"{id_no[:3]}***********{id_no[-4:]}"[: len(id_no)]
