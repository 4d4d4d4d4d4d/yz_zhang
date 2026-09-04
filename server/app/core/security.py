import base64
import hashlib
import hmac
import json
import os
import time

from .config import settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


# 自包含 HMAC-SHA256 签名 token（JWT 同构：payload.signature）
def _sign(payload_b64: bytes) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), payload_b64, hashlib.sha256).hexdigest()


def create_token(user_id: int, session_id: int | None = None) -> str:
    payload = {"sub": user_id, "sid": session_id,
               "exp": int(time.time()) + settings.JWT_EXPIRE_MINUTES * 60}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode())
    return payload_b64.decode() + "." + _sign(payload_b64)


def decode_token(token: str) -> dict:
    """返回 {sub, sid, exp}；签名或过期校验失败抛 ValueError。"""
    payload_b64, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(payload_b64.encode()), signature):
        raise ValueError("bad signature")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    if payload["exp"] < time.time():
        raise ValueError("token expired")
    return payload
