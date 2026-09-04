"""SEC-012/020 + SECEV-001~022 边界防护：全局写限流、失败计数、封禁、人机验证。

设计取向：**新端点默认受保护**。此前的限流是「在每个敏感端点里手写一行
check()」——只有 7 处，任何新端点默认裸奔。这里改为中间件兜底：
所有写操作按 IP 限速，敏感端点再叠加更严的账号+IP 双维度配额。

> **V56 修的是一句说谎的注释。** 这里原本写着「封禁本身落 DB
> （SecurityEvent），因此跨副本仍能看到」——那个表**根本不存在**，
> 封禁就是一个进程内 dict。三副本下的真实后果：攻击者换个连接打到别的副本
> 照样过；有效阈值被放大三倍；管理员解封只解了一个副本，被误封的公司出口 IP
> 之后还有 2/3 概率被拒——**时好时坏的故障比稳定的故障难查一个数量级**。
>
> 注释比代码更容易骗人，因为没有测试盯着它。现在表真的建出来了，
> 并且有测试专门验证「换个进程仍然被封」。
"""
import time
from datetime import timedelta

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .clientip import client_ip
from .config import settings
from .errors import bad_request, forbidden
from .models_security import SecurityEvent
from .ratelimit import check as rl_check

# 封禁快照的本地缓存秒数。封禁时长以分钟计，几秒的滞后对拦截与解封都无所谓；
# 换来的是不必为每个写请求都查一次库。**这是有界最终一致，不是进程内状态**：
# 权威在 DB，任何副本最多滞后这么久就会看到同一份封禁列表。
BAN_CACHE_SECONDS = 5

_ban_cache: dict[str, float] = {}
_ban_cache_at: float = 0.0


def _now():
    from app.modules.account.models import utcnow

    return utcnow()


def _fresh_session():
    """独立会话。

    **认证失败必须写在独立事务里**：登录失败会抛异常，`get_db` 随即回滚整个
    请求事务——用调用方的会话记失败，等于每次失败都被自己抹掉，
    计数永远到不了阈值，封禁永远不会触发。
    """
    from .db import SessionLocal

    return SessionLocal()


# ── SECEV-002 封禁状态以 DB 为准 ──────────────────────────────────
def _refresh_bans() -> dict[str, float]:
    global _ban_cache, _ban_cache_at

    now_ts = time.time()
    if now_ts - _ban_cache_at < BAN_CACHE_SECONDS:
        return _ban_cache
    now = _now()
    try:
        with _fresh_session() as db:
            rows = (
                db.query(SecurityEvent)
                .filter(SecurityEvent.kind == "ban", SecurityEvent.expires_at > now)
                .all()
            )
            _ban_cache = {
                r.ip: max(_ban_cache.get(r.ip, 0.0),
                          now_ts + (r.expires_at - now).total_seconds())
                for r in rows
            }
    except Exception:  # pragma: no cover - 库不可用时不应把全站拦死
        # 安全机制故障时选择放行而不是全拒：限流与网关仍在，
        # 而把所有人挡在门外的代价远大于漏掉几个失败计数
        return _ban_cache
    _ban_cache_at = now_ts
    return _ban_cache


def ban_remaining(ip: str) -> int:
    left = _refresh_bans().get(ip, 0) - time.time()
    return int(left) if left > 0 else 0


def _window_start():
    return _now() - timedelta(seconds=settings.AUTH_FAIL_WINDOW_SECONDS)


def note_auth_failure(ip: str, scope: str = "login", detail: str = "") -> None:
    """SECEV-003 认证失败 +1；窗口内达阈值即封禁。计数与封禁都落 DB。

    **顺序很重要**：调用方在计数**之前**已经检查过封禁（`guard()` 里），
    所以被封的 IP 不会再走到这里。单个 IP 每个窗口最多写入「阈值」条记录，
    攻击者无法靠刷失败把表撑爆（SECEV-004）。改这段时别把顺序换掉。
    """
    global _ban_cache_at

    with _fresh_session() as db:
        db.add(SecurityEvent(kind="auth_failure", ip=ip, scope=scope,
                             detail=detail, created_at=_now()))
        db.flush()
        recent = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.kind == "auth_failure", SecurityEvent.ip == ip,
                    SecurityEvent.created_at >= _window_start())
            .count()
        )
        if recent >= settings.AUTH_FAIL_BAN_THRESHOLD:
            db.add(SecurityEvent(
                kind="ban", ip=ip, scope=scope, created_at=_now(),
                expires_at=_now() + timedelta(seconds=settings.AUTH_FAIL_BAN_SECONDS),
                detail=f"窗口内认证失败 {recent} 次，达到阈值 "
                       f"{settings.AUTH_FAIL_BAN_THRESHOLD}",
            ))
            # 计数清零：封禁期结束后从头开始，而不是一解封就因为旧记录再次被封
            db.query(SecurityEvent).filter(
                SecurityEvent.kind == "auth_failure", SecurityEvent.ip == ip,
            ).delete(synchronize_session=False)
            _ban_cache_at = 0.0     # 立即生效，不等缓存过期
        db.commit()


def note_auth_success(ip: str) -> None:
    """SECEV-005 成功登录清掉窗口内的失败记录——偶发手滑不该累积成封禁。"""
    with _fresh_session() as db:
        db.query(SecurityEvent).filter(
            SecurityEvent.kind == "auth_failure", SecurityEvent.ip == ip,
        ).delete(synchronize_session=False)
        db.commit()


def recent_failures(ip: str) -> int:
    with _fresh_session() as db:
        return (
            db.query(SecurityEvent)
            .filter(SecurityEvent.kind == "auth_failure", SecurityEvent.ip == ip,
                    SecurityEvent.created_at >= _window_start())
            .count()
        )


def unban(db, ip: str, admin_id: int | None = None) -> None:
    """SECEV-021 解封：把封禁改成「已到期」并留痕，**不删记录**。

    删掉就没法回答「这个 IP 什么时候被封过、谁解的」。

    这里用**调用方的会话**（管理端请求本来就持有一个）。开独立会话会和
    请求持有的写锁互相等待——SQLite 下直接是 "database is locked"。
    只有认证失败那条路必须开独立会话，因为它所在的请求随后会回滚。
    """
    global _ban_cache_at

    now = _now()
    db.query(SecurityEvent).filter(
        SecurityEvent.kind == "ban", SecurityEvent.ip == ip,
        SecurityEvent.expires_at > now,
    ).update({"expires_at": now}, synchronize_session=False)
    db.query(SecurityEvent).filter(
        SecurityEvent.kind == "auth_failure", SecurityEvent.ip == ip,
    ).delete(synchronize_session=False)
    db.add(SecurityEvent(kind="unban", ip=ip, user_id=admin_id, created_at=now,
                         detail="管理员人工解封"))
    db.flush()
    _ban_cache.pop(ip, None)
    _ban_cache_at = 0.0


def board() -> dict:
    """SECEV-020 看板：读 DB，所以任何副本看到的都一样。"""
    now = _now()
    with _fresh_session() as db:
        banned = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.kind == "ban", SecurityEvent.expires_at > now)
            .order_by(SecurityEvent.expires_at.desc())
            .limit(200)
            .all()
        )
        failures = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.kind == "auth_failure",
                    SecurityEvent.created_at >= _window_start())
            .all()
        )
        captcha_required = (
            db.query(SecurityEvent)
            .filter(SecurityEvent.kind == "captcha_required",
                    SecurityEvent.created_at >= _window_start())
            .count()
        )
    watching: dict[str, int] = {}
    for row in failures:
        watching[row.ip] = watching.get(row.ip, 0) + 1
    return {
        "banned": [
            {"ip": r.ip, "seconds_left": int((r.expires_at - now).total_seconds()),
             "reason": r.detail}
            for r in banned
        ],
        "watching": sorted(
            ({"ip": ip, "recent_failures": n} for ip, n in watching.items()),
            key=lambda r: -r["recent_failures"],
        )[:50],
        "captcha_required_in_window": captcha_required,
        "threshold": settings.AUTH_FAIL_BAN_THRESHOLD,
        "captcha_after": settings.CAPTCHA_AFTER_FAILURES,
        "ban_seconds": settings.AUTH_FAIL_BAN_SECONDS,
    }


def purge(db, days: int = 30) -> dict:
    """SECEV-006 清理高频噪音；封禁与解封是运营处置留痕，**不清**。"""
    cutoff = _now() - timedelta(days=days)
    removed = (
        db.query(SecurityEvent)
        .filter(SecurityEvent.kind.in_(("auth_failure", "captcha_required",
                                        "captcha_failed", "captcha_passed")),
                SecurityEvent.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    return {"deleted": removed, "kept": "ban/unban 处置记录不随保留期清理"}


def reset() -> None:
    """测试辅助：只清进程内缓存（权威状态在 DB，由测试的建表/清表负责）。"""
    global _ban_cache_at

    _ban_cache.clear()
    _ban_cache_at = 0.0


# ── SECEV-010~014 人机验证 ────────────────────────────────────────
def captcha_required(ip: str) -> bool:
    """SECEV-012 软阈值：失败次数到了就要求验证，但还没到封禁线。

    这个阈值必须**明显低于**封禁阈值，否则这条自证的路等于不存在
    （还没来得及要验证码人就被封了）。
    """
    if settings.CAPTCHA_AFTER_FAILURES <= 0:
        return False
    return recent_failures(ip) >= settings.CAPTCHA_AFTER_FAILURES


def _record(kind: str, ip: str, scope: str, detail: str = "") -> None:
    with _fresh_session() as db:
        db.add(SecurityEvent(kind=kind, ip=ip, scope=scope, detail=detail,
                             created_at=_now()))
        db.commit()


def check_captcha(request, scope: str, token: str) -> None:
    """SECEV-011 达到软阈值后要求人机验证。

    **验证码是给被误伤的人一条自证的路，不是多加一道墙。**
    没有它时，风控的唯一升级手段是封禁——一个手滑输错几次密码的真人，
    和一个撞库脚本，得到的处置完全一样。有了它，升级阶梯变成
    正常 → 要求验证 → 封禁：真人过一下就继续，脚本过不去。
    """
    from app.vendors.registry import get_provider

    ip = client_ip(request)
    if not captcha_required(ip):
        return
    # SECEV-014 即使是直通实现也记录，否则没接真实供应商时风控趋势完全看不见
    _record("captcha_required", ip, scope,
            f"窗口内失败 {recent_failures(ip)} 次")
    provider = get_provider("captcha")
    if provider.verify(token, ip):
        _record("captcha_passed", ip, scope)
        return
    _record("captcha_failed", ip, scope)
    # SECEV-013 验证失败也计入失败计数：否则可以用无限次错误验证码
    # 把真正的登录尝试藏在噪音里
    note_auth_failure(ip, scope, "人机验证未通过")
    raise forbidden("需要完成人机验证后重试", "captcha_required")


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
# **补救入口不能被它要补救的东西挡住。**
# 误封整个公司出口 IP 时，管理员很可能就坐在那个 IP 后面——
# 如果解封接口本身也按 IP 拒绝，这条补救路径恰好在最需要它的时候不可用。
# 这里只放行安全处置路径，它仍然要求管理员身份，不是一扇敞开的门。
BAN_EXEMPT_PREFIXES = ("/api/v1/admin/security",)


class WriteRateLimitMiddleware(BaseHTTPMiddleware):
    """所有写操作按 IP 限速，兜住「新端点忘了加限流」这类遗漏。"""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if request.method not in WRITE_METHODS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)
        if request.headers.get("x-job-token"):
            return await call_next(request)

        ip = client_ip(request)
        left = 0 if path.startswith(BAN_EXEMPT_PREFIXES) else ban_remaining(ip)
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
