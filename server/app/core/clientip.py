"""SEC-011 客户端 IP 解析。

**这是个安全敏感的小函数**：常见错误是直接取 `X-Forwarded-For` 的第一个 IP。
XFF 是客户端可以随便伪造的头——攻击者只要每次请求带一个不同的伪造 IP，
按 IP 的限流与封禁就形同虚设。

正确做法：只信任**我们自己的反代注入的那一跳**。反代会把真实对端 IP
追加到 XFF 末尾，因此从右往左数第 `TRUSTED_PROXY_HOPS` 跳才是可信的。
默认 1 跳（Nginx 直连 api）。没有可信代理时（本地直连）用 socket 对端地址。
"""
from starlette.requests import Request

from .config import settings


def client_ip(request: Request) -> str:
    hops = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        xff = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if len(parts) >= hops:
            # 从右往左第 hops 跳：右侧是离我们最近、由可信代理写入的部分
            return parts[-hops]
        # XFF 比预期短：说明请求没经过预期的代理链，退回对端地址
    peer = request.client.host if request.client else ""
    return peer or "unknown"
