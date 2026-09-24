"""API Key 鉴权与 Webhook 签名/投递（54 号 spec）。"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.errors import bad_request, forbidden
from app.modules.account.models import User, utcnow

from .models import SCOPES, WEBHOOK_EVENTS, ApiKey, Webhook, WebhookDelivery

KEY_PREFIX = "pk_"
# HOOK-001 超过这个时长的请求对端应当拒收——**时间戳必须进签名**，
# 否则攻击者拿一个旧请求原样重放，签名照样对得上。
SIGNATURE_TOLERANCE_SECONDS = 300
# HOOK-002 指数退避
RETRY_SCHEDULE_MINUTES = (1, 5, 30, 120, 720)
MAX_CONSECUTIVE_FAILURES = 5


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_key(db: Session, user: User, name: str, scopes: list[str]) -> tuple[ApiKey, str]:
    """API-001 明文**只在这里出现一次**，之后库里只有哈希。"""
    bad = [s for s in scopes if s not in SCOPES]
    if bad:
        raise bad_request(
            f"不支持的权限范围：{bad}。可用：{'/'.join(SCOPES)}"
            f"（**没有任何动钱的范围**，这是有意的）",
            "invalid_scope",
        )
    if not scopes:
        raise bad_request("必须至少指定一个权限范围", "scope_required")
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    row = ApiKey(user_id=user.id, name=name, key_hash=hash_key(raw),
                 key_prefix=raw[:12], scopes=sorted(scopes))
    db.add(row)
    db.flush()
    return row, raw


def resolve_key(db: Session, raw: str) -> tuple[ApiKey, User]:
    """API-003 Key 的权限**不能超过**它所属用户。

    Key 是用户授权给机器的一个子集，不是独立的权限来源——所以仍要解析出
    用户、仍要过封禁/注销/实名检查。**一个被封禁的用户，他的 API Key
    必须同时失效**，否则封禁只封了人，没封住机器。
    """
    row = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == hash_key(raw), ApiKey.active.is_(True))
        .first()
    )
    if not row:
        raise forbidden("无效的 API Key", "invalid_api_key")
    user = db.get(User, row.user_id)
    if not user:
        raise forbidden("无效的 API Key", "invalid_api_key")
    if user.is_banned:
        raise forbidden("账号已被封禁", "account_banned")
    if user.is_deleted:
        raise forbidden("账号已注销", "account_deleted")
    row.last_used_at = utcnow()
    db.add(row)
    return row, user


def assert_scope(key: ApiKey, needed: str) -> None:
    if needed not in (key.scopes or []):
        raise forbidden(
            f"该 API Key 缺少 `{needed}` 权限范围", "insufficient_scope"
        )


def revoke(db: Session, key: ApiKey) -> ApiKey:
    key.active = False
    key.revoked_at = utcnow()
    db.add(key)
    return key


# ------------------------------------------------------------------ Webhook
def sign(secret: str, timestamp: str, body: str) -> str:
    """HOOK-001 签名把**时间戳也签进去**。

    只签 body 的话，攻击者可以拿一个旧请求原样重放，签名照样对得上。
    """
    mac = hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def verify(secret: str, timestamp: str, body: str, signature: str,
           now: datetime | None = None) -> bool:
    """对端用来验签的参考实现（也供测试直接调用）。"""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int((now or utcnow()).timestamp())
    if abs(current - ts) > SIGNATURE_TOLERANCE_SECONDS:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature or "")


def create_webhook(db: Session, user: User, url: str, events: list[str]) -> Webhook:
    bad = [e for e in events if e not in WEBHOOK_EVENTS]
    if bad:
        raise bad_request(
            f"不支持的事件类型：{bad}。"
            f"事件类型是逐个审过敏感字段才开放的，可用：{'/'.join(WEBHOOK_EVENTS)}",
            "invalid_event",
        )
    if not events:
        raise bad_request("必须至少订阅一个事件", "events_required")
    if not url.startswith("https://"):
        # 明文 http 会让签名保护的内容在链路上可读
        raise bad_request("Webhook 地址必须是 https", "https_required")
    row = Webhook(user_id=user.id, url=url, events=sorted(events),
                  secret=secrets.token_urlsafe(32))
    db.add(row)
    db.flush()
    return row


def enqueue(db: Session, event_type: str, payload: dict) -> int:
    """给所有订阅了该事件的 webhook 排一条投递。

    HOOK-003 **payload 只带标识与状态**，调用方负责不传敏感字段；
    下面再兜一道（见 `_strip_sensitive`）——webhook 的接收端是我们控制不了的，
    一个写进对方日志的手机号，就是我们泄露的手机号。
    """
    if event_type not in WEBHOOK_EVENTS:
        return 0
    safe = _strip_sensitive(payload)
    hooks = db.query(Webhook).filter(Webhook.active.is_(True)).all()
    n = 0
    for h in hooks:
        if event_type not in (h.events or []):
            continue
        db.add(WebhookDelivery(webhook_id=h.id, event_type=event_type,
                               payload=safe, next_attempt_at=utcnow()))
        n += 1
    if n:
        db.flush()
    return n


# HOOK-003 这些字段一律不出站。做成**黑名单兜底 + 调用方白名单**两层：
# 调用方本来就只该传标识与状态，这里是防手滑。
_SENSITIVE_KEYS = {
    "phone", "real_name", "id_number", "id_masked", "address_exact",
    "lat", "lng", "password", "token", "secret", "email",
    "amount_cents", "budget_cents", "balance_cents", "available_cents",
}


def _strip_sensitive(payload: dict) -> dict:
    out = {}
    for k, v in (payload or {}).items():
        if k in _SENSITIVE_KEYS:
            continue
        out[k] = _strip_sensitive(v) if isinstance(v, dict) else v
    return out


def deliver_pending(db: Session, sender=None, limit: int = 50) -> dict:
    """HOOK-002 投递一轮。`sender` 可注入，便于测试与替换 HTTP 客户端。"""
    now = utcnow()
    rows = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.status.in_(("pending", "failed")),
                WebhookDelivery.next_attempt_at <= now)
        .order_by(WebhookDelivery.id)
        .limit(limit)
        .all()
    )
    send = sender or _http_send
    sent = failed = disabled = 0
    for d in rows:
        hook = db.get(Webhook, d.webhook_id)
        if not hook or not hook.active:
            d.status = "dead"
            d.response_excerpt = "webhook 已停用"
            db.add(d)
            continue
        body = json.dumps({"event": d.event_type, "data": d.payload},
                          ensure_ascii=False, sort_keys=True)
        ts = str(int(now.timestamp()))
        d.attempts += 1
        try:
            code, excerpt = send(hook.url, body, ts, sign(hook.secret, ts, body))
        except Exception as exc:
            code, excerpt = 0, f"{type(exc).__name__}"
        d.response_code, d.response_excerpt = code, str(excerpt)[:500]
        if 200 <= code < 300:
            d.status, d.delivered_at = "delivered", now
            hook.consecutive_failures = 0
            sent += 1
        else:
            failed += 1
            hook.consecutive_failures += 1
            if d.attempts >= len(RETRY_SCHEDULE_MINUTES):
                d.status = "dead"
            else:
                d.status = "failed"
                d.next_attempt_at = now + timedelta(
                    minutes=RETRY_SCHEDULE_MINUTES[d.attempts - 1])
            # HOOK-002 一个挂掉的 endpoint 会让重试队列无限堆积，拖慢所有人。
            # 但停用**必须通知到人**——悄悄停掉比不停更坏，
            # 对方会以为平台根本没有事件。
            if hook.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                hook.active = False
                hook.disabled_reason = f"连续 {hook.consecutive_failures} 次投递失败，已自动停用"
                disabled += 1
                _notify_owner(db, hook)
        db.add_all([d, hook])
    return {"sent": sent, "failed": failed, "disabled": disabled,
            "processed": len(rows)}


def _notify_owner(db: Session, hook: Webhook) -> None:
    from app.modules.notification.service import notify

    notify(db, hook.user_id, "system", "Webhook 已自动停用",
           f"{hook.url} 连续投递失败，已停用。修复后可在开发者设置中重新启用。")


def _http_send(url: str, body: str, timestamp: str, signature: str):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body.encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Platform-Timestamp", timestamp)
    req.add_header("X-Platform-Signature", signature)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read(500).decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(500).decode(errors="replace")
