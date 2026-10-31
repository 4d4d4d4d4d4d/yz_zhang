"""CORS-002 响应头声明表与客户端读取的头自动对账（282 号 spec，V309）。

160 号（CORS-001）把客户端要读的响应头登记在 `EXPOSED_HEADERS`，靠的是「新加的头要登记」这句话。
忘了登记的后果只在真浏览器里出现：跨域时读出来是 null，分页总数、剩余次数都看不到。这里扫三端源码里读的响应头，与声明表对账。
"""
import os
import re

HERE = os.path.dirname(__file__)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SOURCES = [os.path.join(REPO, d) for d in ("packages/core/src", "web/src", "app")]
# 浏览器跨域时本来就能读的（CORS-safelisted response headers），不用声明
SAFELISTED = {"cache-control", "content-language", "content-length", "content-type", "expires", "last-modified", "pragma"}
READ = re.compile(r"""\.get\??\.?\(\s*['"]([A-Za-z][A-Za-z0-9-]*)['"]\s*\)""")


def client_reads() -> dict[str, list[str]]:
    """三端非测试源码里 `headers.get('X')` / `headers?.get?.('X')` 读到的头 → 出现在哪些文件。
    只认带连字符的名字或 Retry-After 这类 HTTP 头写法（`Map.get('id')` 这种普通取值不算）。"""
    out: dict[str, list[str]] = {}
    for root in SOURCES:
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", "dist", "build", ".expo")]
            for f in files:
                if not f.endswith((".ts", ".tsx")) or ".test." in f:
                    continue
                path = os.path.join(dirpath, f)
                src = open(path, encoding="utf-8").read()
                for m in READ.finditer(src):
                    name = m.group(1)
                    window = src[max(0, m.start() - 80):m.start()]
                    if "-" in name and "header" in window.lower():
                        out.setdefault(name, []).append(os.path.relpath(path, REPO))
    return out


def test_every_header_the_clients_read_is_exposed():
    from app.main import EXPOSED_HEADERS

    exposed = {h.lower() for h in EXPOSED_HEADERS}
    reads = client_reads()
    assert "X-Total-Count" in reads, "扫描器要认得出 SDK 读分页总数的那一处（否则这条闸门什么都没查）"
    missing = {h: files for h, files in reads.items() if h.lower() not in exposed | SAFELISTED}
    assert not missing, ("这些响应头客户端在读，但没登记在 app/main.py 的 EXPOSED_HEADERS："
                         f"{missing}——跨域时浏览器读出来是 null")
