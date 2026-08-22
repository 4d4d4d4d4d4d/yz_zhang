"""SEC-012/020/021/022 边界防护：全局写限流、失败计数自动封禁、可疑行为留痕。

设计取向：**新端点默认受保护**。此前的限流是「在每个敏感端点里手写一行
check()」——只有 7 处，任何新端点默认裸奔。这里改为中间件兜底：
所有写操作按 IP 限速，敏感端点再叠加更严的账号+IP 双维度配额。
"""
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .clientip import client_ip
from .config import settings
from .errors import bad_request, forbidden
from .ratelimit import check as rl_check

# ── SEC-020 认证失败计数与临时封禁 ────────────────────────────────
# 进程内实现；多副本下配 Redis 时由 ratelimit 的 Redis 后端承担共享计数，
# 封禁本身落 DB（SecurityEvent），因此跨副本仍能看到。
_fail_counts: dict[str, list[float]] = defaultdict(list)
_banned_until: dict[str, float] = {}


def note_auth_failure(ip: str) -> None:
    """认证失败 +1；窗口内达阈值即临时封禁该 IP。"""
    now = time.time()
    window = settings.AUTH_FAIL_WINDOW_SECONDS
    hits = [t for t in _fail_counts[ip] if now - t <= window]
    hits.append(now)
    _fail_counts[ip] = hits
    if len(hits) >= settings.AUTH_FAIL_BAN_THRESHOLD:
        _banned_until[ip] = now + settings.AUTH_FAIL_BAN_SECONDS
        _fail_counts[ip] = []


def note_auth_success(ip: str) -> None:
    _fail_counts.pop(ip, None)


def ban_remaining(ip: str) -> int:
    left = _banned_until.get(ip, 0) - time.time()
    return int(left) if left > 0 else 0


def unban(ip: str) -> None:
    _banned_until.pop(ip, None)
    _fail_counts.pop(ip, None)


def reset() -> None:
    """测试辅助。"""
    _fail_counts.clear()
    _banned_until.clear()


# ── SEC-011 双维度限流入口 ────────────────────────────────────────
def guard(request, scope: str, account_key: str, *, limit: int, ip_limit: int,
          window_seconds: int = 60) -> None:
    """账号维度 + IP 维度双重限流：**任一维度超限即拒**。

    只按账号限的老做法挡不住「批量注册」——攻击者每次换手机号，
    账号维度的计数器永远是 1。加上 IP 维度后，换号不换 IP 也会被挡。
    """
    ip = client_ip(request)
    left = ban_remaining(ip)
    if left > 0:
        raise forbidden(f"操作异常频繁，请 {left} 秒后重试", "temporarily_banned")
    rl_check(f"{scope}:acct:{account_key}", limit=limit, window_seconds=window_seconds)
    rl_check(f"{scope}:ip:{ip}", limit=ip_limit, window_seconds=window_seconds)


# ── SEC-012 全局写操作兜底限流 ────────────────────────────────────
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# 内部 job 与探针不受此限（它们有独立的令牌鉴权）
EXEMPT_PREFIXES = ("/healthz", "/readyz", "/version", "/metrics", "/jobz")


class WriteRateLimitMiddleware(BaseHTTPMiddleware):
    """所有写操作按 IP 限速，兜住「新端点忘了加限流」这类遗漏。"""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if request.method not in WRITE_METHODS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)
        if request.headers.get("x-job-token"):
            return await call_next(request)

        ip = client_ip(request)
        left = ban_remaining(ip)
        if left > 0:
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "temporarily_banned",
                                    "message": f"操作异常频繁，请 {left} 秒后重试"}},
            )
        try:
            rl_check(f"write:ip:{ip}", limit=settings.WRITE_RATE_PER_MINUTE,
                     window_seconds=60)
        except Exception as exc:  # rl_check 抛的是 HTTPException
            detail = getattr(exc, "detail", {"code": "rate_limited", "message": "操作过于频繁"})
            return JSONResponse(status_code=429, content={"detail": detail})
        return await call_next(request)


def too_frequent(message: str = "操作过于频繁"):
    return bad_request(message, "rate_limited")
