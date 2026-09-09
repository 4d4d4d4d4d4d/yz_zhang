"""VND-031 对象存储供应商。

上传走 base64 JSON 而非 multipart：客户端本来就要先压缩再传（MOB-021），
压缩后的体积在 base64 下仍很小，换来的是不引入额外依赖、且与现有
JSON + 幂等键 + 鉴权的请求管线完全一致。真实供应商实现应改为
「签发直传 URL，文件不经过平台」——接口已按这个形态预留 `sign_upload`。
"""
import base64
import hashlib
import os
import secrets
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
        """FILE-010/011 名字随机，磁盘按内容去重。

        改造前名字是 `sha256(data)[:32]`——**文件名就是文件内容的指纹**。
        读取端点是匿名的（CDN 直出时也只能是匿名的），靠的是「URL 不可猜」
        这个能力 URL 前提；而内容哈希对任何持有这份内容的人都是公开的，
        于是这个端点变成一台存在性预言机：拿着一张候选图片离线算一次
        sha256，就能问平台「这张图在不在你这儿」。

        省空间是对的，但省的应该是**磁盘**，不是 URL。这里把两件事拆开：
        blob 按内容哈希存一份，每次上传各给一个随机名，用硬链接指过去。
        引用计数顺带解决了删除困境——删掉甲的名字，乙的名字仍然有效。
        """
        ext = ALLOWED[content_type]
        digest = hashlib.sha256(data).hexdigest()
        blob_dir = os.path.join(self.root, "blobs")
        os.makedirs(blob_dir, exist_ok=True)
        blob = os.path.join(blob_dir, digest)
        if not os.path.exists(blob):
            tmp = blob + ".tmp"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, blob)       # 同目录原子替换，避免读到半个文件

        name = f"{secrets.token_hex(16)}{ext}"   # 128 位 CSPRNG，与内容无关
        path = os.path.join(self.root, name)
        try:
            os.link(blob, path)
        except OSError:
            # 跨设备/不支持硬链接：退化为复制。只损失空间，不损失正确性。
            with open(path, "wb") as f:
                f.write(data)
        return VendorResult(ok=True, external_ref=name,
                            data={"url": f"/api/v1/files/{name}", "sha256": digest})

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
