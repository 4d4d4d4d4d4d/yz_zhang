"""开发者设置（会话鉴权）+ 开放 API（Key 鉴权）（54 号 spec）。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, forbidden, not_found
from app.core.locks import job_slot
from app.core.timefmt import iso
from app.modules.account.models import User

from . import service, usage
from .deps import require_scope
from .models import (
    SCOPE_LABELS,
    SCOPES,
    WEBHOOK_EVENTS,
    ApiKey,
    Webhook,
    WebhookDelivery,
)

router = APIRouter(tags=["openapi"])


class KeyIn(BaseModel):
    name: str = Field(default="", max_length=60)
    scopes: list[str] = Field(default_factory=list)


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(default_factory=list)


# ------------------------------------------------ 开发者设置（用户会话鉴权）
@router.get("/developer/scopes")
def list_scopes():
    """公开：让集成方知道有哪些权限范围，以及**为什么没有动钱的那一档**。"""
    return {
        "scopes": [{"key": s, "label": SCOPE_LABELS[s]} for s in SCOPES],
        "events": list(WEBHOOK_EVENTS),
        "notice": (
            "**没有任何可以动钱的权限范围**。出金是这个平台上唯一不可逆的动作，"
            "而集成密钥泄露的概率远高于用户密码（它躺在 CI 变量、日志、截图里）。"
        ),
    }


@router.post("/developer/api-keys", status_code=201)
def create_key(body: KeyIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db, scope="function")):
    """API-001 明文 key **只在这个响应里出现一次**。"""
    row, raw = service.issue_key(db, user, body.name, body.scopes)
    return {
        "id": row.id, "name": row.name, "scopes": row.scopes,
        "key_prefix": row.key_prefix,
        "key": raw,
        "warning": "这是**唯一一次**显示完整密钥。库里只存哈希，丢了只能轮换重发。",
    }


@router.get("/developer/api-keys")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = (db.query(ApiKey).filter(ApiKey.user_id == user.id)
            .order_by(ApiKey.id.desc()).all())
    return [
        {"id": r.id, "name": r.name, "scopes": r.scopes, "key_prefix": r.key_prefix,
         "active": r.active,
         "last_used_at": iso(r.last_used_at),
         "created_at": iso(r.created_at),
         # API-050（145 号 spec）：自己设的上限（0 = 用平台默认）与生效的上限
         "rate_per_minute": r.rate_per_minute, "effective_rate_per_minute": service.effective_rate(r),
         # API-052（152 号 spec）：自己设的每日配额（0 = 用平台默认）与生效的配额
         "daily_quota": r.daily_quota, "effective_daily_quota": usage.effective_quota(r)}
        for r in rows
    ]


class RateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rate_per_minute: int = Field(ge=0, le=100_000)


@router.put("/developer/api-keys/{key_id}/rate-limit")
def set_key_rate(key_id: int, body: RateIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db, scope="function")):
    """API-050 给自己的 Key 设一个更低的每分钟上限（例如只给测试环境用的 Key）；0 = 恢复平台默认。
    不能设得比平台默认高：需要更高额度要找平台。"""
    from app.core.config import settings

    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise not_found("密钥不存在")
    cap = settings.API_KEY_RATE_PER_MINUTE
    if body.rate_per_minute > cap:
        raise bad_request(f"每分钟上限不能超过平台默认的 {cap} 次；需要更高额度请联系平台", "api_key_rate_above_cap")
    row.rate_per_minute = body.rate_per_minute
    return {"id": row.id, "rate_per_minute": row.rate_per_minute, "effective_rate_per_minute": service.effective_rate(row)}


class QuotaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_quota: int = Field(ge=0, le=10_000_000)


@router.put("/developer/api-keys/{key_id}/quota")
def set_key_quota(key_id: int, body: QuotaIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    """API-052 给自己的 Key 设一个更低的每日配额（例如测试环境的 Key 一天 500 次就够）；0 = 恢复平台默认。
    不能设得比平台默认高：需要更高配额要找平台。"""
    from app.core.config import settings

    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise not_found("密钥不存在")
    cap = settings.API_KEY_DAILY_QUOTA
    if body.daily_quota > cap:
        raise bad_request(f"每日配额不能超过平台默认的 {cap} 次；需要更高配额请联系平台", "api_key_quota_above_cap")
    row.daily_quota = body.daily_quota
    return {"id": row.id, "daily_quota": row.daily_quota, "effective_daily_quota": usage.effective_quota(row)}


@router.get("/developer/api-keys/{key_id}/usage")
def key_usage(key_id: int, days: int = Query(14, ge=1, le=90), user: User = Depends(get_current_user),
              db: Session = Depends(get_db, scope="function")):
    """API-052 这把 Key 每天（北京时间）用了多少、被挡回去多少，今天还剩多少、几点恢复。最近的一天在前。"""
    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise not_found("密钥不存在")
    return usage.view(db, row, days)


@router.delete("/developer/api-keys/{key_id}")
def revoke_key(key_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db, scope="function")):
    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise not_found("密钥不存在")
    service.revoke(db, row)
    return {"id": row.id, "active": row.active}


@router.post("/developer/api-keys/{key_id}/rotate", status_code=201)
def rotate_key(key_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db, scope="function")):
    """轮换：生成新 key，**旧 key 立刻失效**。

    因为明文找不回来，轮换是「丢了怎么办」的唯一出路，必须提供。
    """
    old = db.get(ApiKey, key_id)
    if not old or old.user_id != user.id:
        raise not_found("密钥不存在")
    service.revoke(db, old)
    row, raw = service.issue_key(db, user, old.name, list(old.scopes or []))
    row.rate_per_minute = old.rate_per_minute   # API-050 轮换不改额度
    row.daily_quota = old.daily_quota           # API-052 轮换不改配额，也不清零当天用量
    db.flush()
    usage.carry_today(db, old.id, row.id)
    return {"id": row.id, "key": raw, "revoked_id": old.id,
            "warning": "旧密钥已立即失效；新密钥同样只显示这一次。"}


@router.post("/developer/webhooks", status_code=201)
def create_webhook(body: WebhookIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    row = service.create_webhook(db, user, body.url, body.events)
    return {
        "id": row.id, "url": row.url, "events": row.events,
        "secret": row.secret,
        "signature_howto": (
            "验签：HMAC-SHA256(secret, f\"{X-Platform-Timestamp}.{原始 body}\")，"
            "与 X-Platform-Signature 比对；并拒收时间戳偏差超过 300 秒的请求"
            "（**时间戳必须参与签名**，否则旧请求可被原样重放）。"
        ),
    }


@router.get("/developer/webhooks")
def list_webhooks(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = db.query(Webhook).filter(Webhook.user_id == user.id).all()
    return [
        {"id": r.id, "url": r.url, "events": r.events, "active": r.active,
         "consecutive_failures": r.consecutive_failures,
         "disabled_reason": r.disabled_reason}
        for r in rows
    ]


@router.get("/developer/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db, scope="function")):
    """HOOK-002 投递记录。

    没有记录的话，集成方报「我没收到」时平台只能说「我发了」——
    两边都无法证明，这种争执没有出口。
    """
    hook = db.get(Webhook, webhook_id)
    if not hook or hook.user_id != user.id:
        raise not_found("Webhook 不存在")
    rows = (db.query(WebhookDelivery)
            .filter(WebhookDelivery.webhook_id == webhook_id)
            .order_by(WebhookDelivery.id.desc()).limit(100).all())
    return [
        {"id": r.id, "event_type": r.event_type, "status": r.status,
         "attempts": r.attempts, "response_code": r.response_code,
         "response_excerpt": r.response_excerpt,
         "created_at": iso(r.created_at)}
        for r in rows
    ]


@router.delete("/developer/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db, scope="function")):
    hook = db.get(Webhook, webhook_id)
    if not hook or hook.user_id != user.id:
        raise not_found("Webhook 不存在")
    db.delete(hook)
    return {"deleted": webhook_id}


# ------------------------------------------------------ 开放 API（Key 鉴权）
@router.get("/open/v1/tasks")
def open_list_tasks(limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
                    marketplace: bool = False,
                    principal=Depends(require_scope("tasks:read")),
                    db: Session = Depends(get_db, scope="function")):
    from app.modules.task.models import Task

    _key, user = principal
    visible = (Task.status == "published") & (Task.visibility == "public") if marketplace else \
        or_(Task.creator_id == user.id, Task.executor_id == user.id)
    rows = (db.query(Task).filter(visible)
            .order_by(Task.id.desc()).offset(offset).limit(min(limit, 100)).all())
    return [
        {"id": t.id, "title": t.title, "category": t.category, "status": t.status,
         "budget_cents": t.budget_cents, "executor_id": t.executor_id,
         "created_at": iso(t.created_at)}
        for t in rows
    ]


@router.get("/open/v1/tasks/{task_id}")
def open_get_task(task_id: int, marketplace: bool = False, principal=Depends(require_scope("tasks:read")),
                  db: Session = Depends(get_db, scope="function")):
    from app.modules.task.models import Task

    _key, user = principal
    t = db.get(Task, task_id)
    if not t or (user.id not in (t.creator_id, t.executor_id)
                 and not (marketplace and t.visibility == "public" and t.status == "published")):
        raise not_found("任务不存在")
    return {"id": t.id, "title": t.title, "description": t.description,
            "category": t.category, "status": t.status,
            "budget_cents": t.budget_cents, "executor_id": t.executor_id,
            "acceptance_criteria": t.acceptance_criteria,
            "created_at": iso(t.created_at)}


@router.get("/open/v1/wallet")
def open_wallet(principal=Depends(require_scope("wallet:read")),
                db: Session = Depends(get_db, scope="function")):
    from app.modules.wallet import service as wallet

    _key, user = principal
    acct = wallet.get_or_create(db, user.id)
    return {"available_cents": acct.available_cents,
            "escrow_cents": acct.escrow_cents,
            "frozen_cents": acct.frozen_cents}


@router.post("/openapi/jobs/purge-usage")
def run_purge_usage(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                    __=Depends(job_slot("api_usage_purge"), scope="function")):
    """API-055 清掉 90 天以前的 Key 用量记录（一天一次）。"""
    from .usage import purge_usage

    return purge_usage(db)


@router.post("/openapi/jobs/deliver-webhooks")
def run_deliver(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                __=Depends(job_slot("deliver_webhooks"), scope="function")):
    return service.deliver_pending(db)
