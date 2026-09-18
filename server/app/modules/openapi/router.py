"""开发者设置（会话鉴权）+ 开放 API（Key 鉴权）（54 号 spec）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import forbidden, not_found
from app.core.locks import job_slot
from app.modules.account.models import User

from . import service
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
               db: Session = Depends(get_db)):
    """API-001 明文 key **只在这个响应里出现一次**。"""
    row, raw = service.issue_key(db, user, body.name, body.scopes)
    return {
        "id": row.id, "name": row.name, "scopes": row.scopes,
        "key_prefix": row.key_prefix,
        "key": raw,
        "warning": "这是**唯一一次**显示完整密钥。库里只存哈希，丢了只能轮换重发。",
    }


@router.get("/developer/api-keys")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(ApiKey).filter(ApiKey.user_id == user.id)
            .order_by(ApiKey.id.desc()).all())
    return [
        {"id": r.id, "name": r.name, "scopes": r.scopes, "key_prefix": r.key_prefix,
         "active": r.active,
         "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.delete("/developer/api-keys/{key_id}")
def revoke_key(key_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row or row.user_id != user.id:
        raise not_found("密钥不存在")
    service.revoke(db, row)
    return {"id": row.id, "active": row.active}


@router.post("/developer/api-keys/{key_id}/rotate", status_code=201)
def rotate_key(key_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """轮换：生成新 key，**旧 key 立刻失效**。

    因为明文找不回来，轮换是「丢了怎么办」的唯一出路，必须提供。
    """
    old = db.get(ApiKey, key_id)
    if not old or old.user_id != user.id:
        raise not_found("密钥不存在")
    service.revoke(db, old)
    row, raw = service.issue_key(db, user, old.name, list(old.scopes or []))
    return {"id": row.id, "key": raw, "revoked_id": old.id,
            "warning": "旧密钥已立即失效；新密钥同样只显示这一次。"}


@router.post("/developer/webhooks", status_code=201)
def create_webhook(body: WebhookIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
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
def list_webhooks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Webhook).filter(Webhook.user_id == user.id).all()
    return [
        {"id": r.id, "url": r.url, "events": r.events, "active": r.active,
         "consecutive_failures": r.consecutive_failures,
         "disabled_reason": r.disabled_reason}
        for r in rows
    ]


@router.get("/developer/webhooks/{webhook_id}/deliveries")
def list_deliveries(webhook_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
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
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.delete("/developer/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    hook = db.get(Webhook, webhook_id)
    if not hook or hook.user_id != user.id:
        raise not_found("Webhook 不存在")
    db.delete(hook)
    return {"deleted": webhook_id}


# ------------------------------------------------------ 开放 API（Key 鉴权）
@router.get("/open/v1/tasks")
def open_list_tasks(limit: int = 20, offset: int = 0,
                    principal=Depends(require_scope("tasks:read")),
                    db: Session = Depends(get_db)):
    from app.modules.task.models import Task

    _key, user = principal
    rows = (db.query(Task).filter(Task.creator_id == user.id)
            .order_by(Task.id.desc()).offset(offset).limit(min(limit, 100)).all())
    return [
        {"id": t.id, "title": t.title, "category": t.category, "status": t.status,
         "budget_cents": t.budget_cents, "executor_id": t.executor_id,
         "created_at": t.created_at.isoformat()}
        for t in rows
    ]


@router.get("/open/v1/tasks/{task_id}")
def open_get_task(task_id: int, principal=Depends(require_scope("tasks:read")),
                  db: Session = Depends(get_db)):
    from app.modules.task.models import Task

    _key, user = principal
    t = db.get(Task, task_id)
    if not t or t.creator_id != user.id:
        raise not_found("任务不存在")
    return {"id": t.id, "title": t.title, "description": t.description,
            "category": t.category, "status": t.status,
            "budget_cents": t.budget_cents, "executor_id": t.executor_id,
            "acceptance_criteria": t.acceptance_criteria,
            "created_at": t.created_at.isoformat()}


@router.get("/open/v1/wallet")
def open_wallet(principal=Depends(require_scope("wallet:read")),
                db: Session = Depends(get_db)):
    from app.modules.wallet import service as wallet

    _key, user = principal
    acct = wallet.get_or_create(db, user.id)
    return {"available_cents": acct.available_cents,
            "escrow_cents": acct.escrow_cents,
            "frozen_cents": acct.frozen_cents}


@router.post("/openapi/jobs/deliver-webhooks")
def run_deliver(db: Session = Depends(get_db), _=Depends(require_job_auth),
                __=Depends(job_slot("deliver_webhooks"))):
    return service.deliver_pending(db)
