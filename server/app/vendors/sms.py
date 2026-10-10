"""VND-020/021 短信供应商。"""
import hashlib
import hmac
import secrets
import uuid
from typing import Protocol

from app.core.config import settings

from .base import VendorResult


class SmsProvider(Protocol):
    name: str
    echoes_code: bool  # 是否可回显明文验证码（仅 Mock 为 True）

    def send_code(self, phone: str, code: str, template: str = "verify") -> VendorResult: ...


class MockSmsProvider:
    """开发/CI 缺省：不真的发短信，验证码固定为 `settings.DEV_SMS_CODE`。"""

    name = "mock"
    echoes_code = True

    def send_code(self, phone: str, code: str, template: str = "verify") -> VendorResult:
        return VendorResult(
            ok=True, external_ref=f"mock-sms-{uuid.uuid4().hex[:10]}",
            data={"template": template},
        )


def generate_code() -> str:
    """VND-021 验证码由服务端生成（真实通道下随机；Mock 下固定便于测试）。"""
    provider_is_mock = settings.SMS_PROVIDER == "mock"
    return settings.DEV_SMS_CODE if provider_is_mock else f"{secrets.randbelow(1000000):06d}"


def hash_code(phone: str, code: str) -> str:
    """VND-021 验证码只存哈希（绑定手机号加盐），泄库也无法直接冒用。"""
    return hmac.new(settings.JWT_SECRET.encode(), f"{phone}:{code}".encode(),
                    hashlib.sha256).hexdigest()
