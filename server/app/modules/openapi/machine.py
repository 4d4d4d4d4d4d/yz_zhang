"""Bounded machine task delegation. The authorizing user remains the principal.

No mandate grants signing, funding, acceptance, withdrawals or legal equity rights.
Every write requires an idempotency key and consumes a lifetime exposure allowance.
"""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base, get_db
from app.core.deps import get_current_user, require_verified
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow
from app.modules.task import router as task_api
from app.modules.task.models import Task
from .deps import require_scope
from .models import ApiKey

router = APIRouter(tags=['machine-delegation'])


class MachineMandate(Base):
    __tablename__ = 'machine_mandates'
    key_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    principal_id: Mapped[int] = mapped_column(Integer, index=True)
    operations: Mapped[list] = mapped_column(JSON)
    categories: Mapped[list] = mapped_column(JSON)
    per_task_cents: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    used_cents: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MachineAction(Base):
    __tablename__ = 'machine_actions'
    __table_args__ = (UniqueConstraint('key_id', 'request_key', name='uq_machine_request'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[int] = mapped_column(Integer, index=True)
    principal_id: Mapped[int] = mapped_column(Integer, index=True)
    request_key: Mapped[str] = mapped_column(String(80))
    operation: Mapped[str] = mapped_column(String(20))
    task_id: Mapped[int] = mapped_column(Integer)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class MandateIn(BaseModel):
    operations: list[Literal['publish', 'apply', 'deliver']] = Field(min_length=1, max_length=3)
    categories: list[str] = Field(min_length=1, max_length=20)
    per_task_cents: int = Field(gt=0, le=100_000_000)
    total_cents: int = Field(gt=0, le=1_000_000_000)
    valid_days: int = Field(ge=1, le=90)
    acknowledge_responsibility: Literal[True]


def _own_key(db, key_id, user):
    key = db.get(ApiKey, key_id)
    if not key or key.user_id != user.id:
        raise not_found('密钥不存在')
    return key


def _dump(row):
    return {'key_id': row.key_id, 'principal_id': row.principal_id,
            'operations': row.operations, 'categories': row.categories,
            'per_task_cents': row.per_task_cents, 'total_cents': row.total_cents,
            'used_cents': row.used_cents, 'expires_at': iso(row.expires_at)}


@router.post('/developer/api-keys/{key_id}/mandate', status_code=201)
def grant(key_id: int, body: MandateIn, user: User = Depends(require_verified),
          db: Session = Depends(get_db)):
    from app.modules.legal.consent import require_current_agreement
    require_current_agreement(db, user.id)
    key = _own_key(db, key_id, user)
    if not key.active or 'tasks:write' not in key.scopes:
        raise forbidden('需要有效的 tasks:write 密钥')
    # Serialize grant, rotate and revoke on this credential.
    if db.query(ApiKey).filter_by(id=key_id, active=True).update({'last_used_at': utcnow()}) != 1:
        raise forbidden('密钥已吊销', 'invalid_api_key')
    if db.get(MachineMandate, key_id):
        raise conflict('授权不可原地扩权；请吊销旧密钥并重新授权', 'mandate_exists')
    if body.total_cents < body.per_task_cents or any(not x.strip() for x in body.categories):
        raise bad_request('累计额度不得低于单笔额度，类目不能为空')
    row = MachineMandate(key_id=key_id, principal_id=user.id,
        operations=sorted(set(body.operations)), categories=sorted(set(body.categories)),
        per_task_cents=body.per_task_cents, total_cents=body.total_cents,
        expires_at=utcnow()+timedelta(days=body.valid_days))
    db.add(row)
    db.flush()
    return _dump(row)


@router.get('/developer/api-keys/{key_id}/mandate')
def get_mandate(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own_key(db, key_id, user)
    row = db.get(MachineMandate, key_id)
    return _dump(row) if row else None


@router.get('/developer/api-keys/{key_id}/actions')
def actions(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _own_key(db, key_id, user)
    rows = db.query(MachineAction).filter_by(key_id=key_id).order_by(MachineAction.id.desc()).limit(100).all()
    return [{'id': x.id, 'key_id': x.key_id, 'principal_id': x.principal_id,
             'operation': x.operation, 'task_id': x.task_id, 'fingerprint': x.fingerprint,
             'created_at': iso(x.created_at)} for x in rows]


def _run(db, principal, operation, request_key, params, category, exposure, run):
    key, user = principal
    if not request_key or len(request_key) > 80:
        raise bad_request('机器写操作必须携带 1—80 字符的 Idempotency-Key', 'idempotency_required')
    require_verified(user=user, db=db)
    # An UPDATE acquires a row write lock on Postgres, and serializes SQLite writers.
    changed = db.query(ApiKey).filter_by(id=key.id, active=True).update({'last_used_at': utcnow()})
    if changed != 1:
        raise forbidden('密钥已吊销', 'invalid_api_key')
    db.flush()
    mandate = db.get(MachineMandate, key.id)
    if not mandate or mandate.expires_at <= utcnow() or operation not in mandate.operations:
        raise forbidden('机器授权不存在、过期或不包含此操作', 'mandate_required')
    fingerprint = hashlib.sha256(json.dumps({'operation':operation,'params':params},
        sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    old = db.query(MachineAction).filter_by(key_id=key.id, request_key=request_key).first()
    if old:
        if old.fingerprint != fingerprint:
            raise conflict('幂等键对应的参数已变化', 'idempotency_key_conflict')
        return old.response
    if category not in mandate.categories:
        raise forbidden('任务类目不在授权范围', 'mandate_category')
    if exposure < 0 or exposure > mandate.per_task_cents or mandate.used_cents + exposure > mandate.total_cents:
        raise forbidden('超过单笔或累计任务授权额度', 'mandate_budget')
    result = run()
    mandate.used_cents += exposure
    db.add(MachineAction(key_id=key.id, principal_id=user.id, request_key=request_key,
        operation=operation, task_id=result['task_id'] if 'task_id' in result else result['id'],
        fingerprint=fingerprint, response=result))
    db.flush()
    return result


@router.post('/open/v1/tasks', status_code=201)
def publish(body: task_api.TaskIn, principal=Depends(require_scope('tasks:write')),
            db: Session = Depends(get_db), idempotency_key: str = Header(default='')):
    if body.people_needed != 1 or body.recurrence != 'none':
        raise bad_request('机器授权仅支持单次单名额任务，批量或周期任务需分别授权')
    if body.budget_cents <= 0 or body.deposit_cents < 0:
        raise bad_request('预算必须为正且保证金不能为负')
    return _run(db, principal, 'publish', idempotency_key, body.model_dump(mode='json'),
        body.category, body.budget_cents+body.bonus_cents,
        lambda: task_api.create_task(body, principal[1], db))


@router.post('/open/v1/tasks/{task_id}/applications', status_code=201)
def apply(task_id: int, body: task_api.ApplyIn, principal=Depends(require_scope('tasks:write')),
          db: Session = Depends(get_db), idempotency_key: str = Header(default='')):
    task = db.get(Task, task_id)
    if not task or task.visibility != 'public':
        raise not_found('任务不存在')
    if body.bid_cents < 0:
        raise bad_request('报价不能为负')
    exposure = max(body.bid_cents or task.budget_cents, task.budget_cents+task.bonus_cents, task.deposit_cents)
    def run():
        result = task_api.apply(task_id, body, principal[1], db)
        return {**result, 'task_id':task_id}
    return _run(db, principal, 'apply', idempotency_key,
        {'task_id':task_id, **body.model_dump()}, task.category, exposure, run)


@router.post('/open/v1/tasks/{task_id}/deliver')
def deliver(task_id: int, body: task_api.DeliverIn, principal=Depends(require_scope('tasks:write')),
            db: Session = Depends(get_db), idempotency_key: str = Header(default='')):
    task = db.get(Task, task_id)
    if not task or task.executor_id != principal[1].id:
        raise not_found('任务不存在')
    def run():
        result = task_api.deliver(task_id, body, principal[1], db)
        return {**result, 'task_id':task_id}
    return _run(db, principal, 'deliver', idempotency_key,
        {'task_id':task_id, **body.model_dump()}, task.category,
        max(task.budget_cents+task.bonus_cents, task.deposit_cents), run)
