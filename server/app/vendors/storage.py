"""VND-031 对象存储供应商。

上传走 base64 JSON 而非 multipart：客户端本来就要先压缩再传（MOB-021），
压缩后的体积在 base64 下仍很小，换来的是不引入额外依赖、且与现有
JSON + 幂等键 + 鉴权的请求管线完全一致。真实供应商实现应改为
「签发直传 URL，文件不经过平台」——接口已按这个形态预留 `sign_upload`。
"""
import base64
import hashlib
import os
import uuid
from typing import Protocol

from .base import VendorError, VendorResult

# 白名单而非黑名单：只认这几种图片，其余一律拒绝
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_BYTES = 2 * 1024 * 1024  # 2MB（客户端压缩后应远小于此）

# 魔数校验：仅信 Content-Type 等于让调用方自证清白
_MAGIC = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class StorageProvider(Protocol):
    name: str

    def put(self, data: bytes, content_type: str) -> VendorResult:
        """存入并返回可访问的相对 URL。"""

    def sign_upload(self, content_type: str) -> VendorResult:
        """真实供应商：签发直传 URL（文件不经过平台）。"""


class LocalStorageProvider:
    """开发/CI 缺省：落本地目录，由应用自身提供读取端点。"""

    name = "local"

    def __init__(self, root: str | None = None) -> None:
        self.root = root or os.environ.get("PLATFORM_UPLOAD_DIR", "./data/uploads")

    def put(self, data: bytes, content_type: str) -> VendorResult:
        ext = ALLOWED[content_type]
        # 内容寻址：同一张图重复上传不会占两份空间
        digest = hashlib.sha256(data).hexdigest()[:32]
        name = f"{digest}{ext}"
        os.makedirs(self.root, exist_ok=True)
        path = os.path.join(self.root, name)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        return VendorResult(ok=True, external_ref=name, data={"url": f"/api/v1/files/{name}"})

    def sign_upload(self, content_type: str) -> VendorResult:  # pragma: no cover - 本地不用直传
        return VendorResult(ok=True, external_ref=uuid.uuid4().hex,
                            data={"direct_upload": False})

    def read(self, name: str) -> tuple[bytes, str] | None:
        # 只允许 basename，杜绝 ../ 穿越
        if name != os.path.basename(name):
            return None
        ext = os.path.splitext(name)[1]
        content_type = next((k for k, v in ALLOWED.items() if v == ext), None)
        if not content_type:
            return None
        path = os.path.join(self.root, name)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read(), content_type


def decode_upload(data_b64: str, content_type: str) -> bytes:
    """解码并校验：类型白名单 + 大小上限 + 魔数一致。"""
    if content_type not in ALLOWED:
        raise VendorError("unsupported_type", "仅支持 JPEG / PNG / WebP 图片", retryable=False)
    # base64 每 4 字符还原 3 字节，先按长度粗筛，避免先解码一个巨大的串
    if len(data_b64) // 4 * 3 > MAX_BYTES:
        raise VendorError("too_large", f"图片超过 {MAX_BYTES // 1024 // 1024}MB 上限",
                          retryable=False)
    try:
        raw = base64.b64decode(data_b64, validate=True)
    except Exception as exc:
        raise VendorError("bad_encoding", "图片数据格式不正确", retryable=False) from exc
    if len(raw) > MAX_BYTES:
        raise VendorError("too_large", f"图片超过 {MAX_BYTES // 1024 // 1024}MB 上限",
                          retryable=False)
    if not any(raw.startswith(m) for m in _MAGIC[content_type]):
        raise VendorError("type_mismatch", "文件内容与声明的类型不符", retryable=False)
    return raw
