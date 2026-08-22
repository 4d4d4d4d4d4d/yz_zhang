"""VND-020/021 短信验证码编排：生成 → 只存哈希 → 发送 → 校验。

模拟通道下验证码固定（`DEV_SMS_CODE`），校验直接放行，保持既有测试与
演示体验不变；接真实通道后自动切到「必须先请求验证码、有效期与尝试次数
受限」的严格路径，业务代码不改。
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request
from app.modules.account.models import utcnow

from . import base
from .models import SmsCode
from .registry import get_provider
from .sms import generate_code, hash_code

CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5


def send_code(db: Session, phone: str, scene: str = "verify") -> dict:
    """发送验证码。同一手机号+场景的旧码作废（只保留最新一条有效）。"""
    provider = get_provider("sms")
    code = generate_code()
    db.query(SmsCode).filter(SmsCode.phone == phone, SmsCode.scene == scene,
                             SmsCode.consumed.is_(False)).update({"consumed": True})
    row = SmsCode(
        phone=phone, scene=scene, code_hash=hash_code(phone, code),
        expires_at=utcnow() + timedelta(minutes=CODE_TTL_MINUTES),
    )
    db.add(row)
    db.flush()

    base.call(
        db, "sms", provider.name, "send_code", {"phone": phone, "code": code, "scene": scene},
        lambda: provider.send_code(phone, code, scene),
        idem_key=f"sms:{phone}:{scene}:{row.id}",
    )
    out = {"sent": True, "expires_in": CODE_TTL_MINUTES * 60}
    if getattr(provider, "echoes_code", False):
        out["dev_code"] = code  # 仅模拟通道回显，真实通道永不返回明文
    return out


def verify_code(db: Session, phone: str, code: str, scene: str = "verify") -> None:
    """校验并消费验证码；不通过抛 400 `sms_code_invalid`。"""
    provider = get_provider("sms")
    if getattr(provider, "echoes_code", False):
        # 模拟通道：固定码直通（无需先调用 send-code），保持开发/CI 体验
        if code != settings.DEV_SMS_CODE:
            raise bad_request("验证码错误", "sms_code_invalid")
        return

    row = (
        db.query(SmsCode)
        .filter(SmsCode.phone == phone, SmsCode.scene == scene, SmsCode.consumed.is_(False))
        .order_by(SmsCode.id.desc())
        .first()
    )
    if not row:
        raise bad_request("请先获取验证码", "sms_code_missing")
    if row.expires_at <= utcnow():
        raise bad_request("验证码已过期，请重新获取", "sms_code_expired")
    if row.attempts >= MAX_ATTEMPTS:
        raise bad_request("验证码尝试次数过多，请重新获取", "sms_code_locked")
    row.attempts += 1
    db.add(row)
    if row.code_hash != hash_code(phone, code):
        db.flush()
        raise bad_request("验证码错误", "sms_code_invalid")
    row.consumed = True
    db.add(row)
    db.flush()
