from datetime import timedelta
from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.openapi.machine import MachineMandate, MachineAction
from app.modules.task.models import Task
from tests.conftest import register, auth, verify_user


def setup(client, operations=None):
    user=register(client,'13900880101','机器责任人')
    verify_user(client,user)
    key=client.post('/api/v1/developer/api-keys',headers=auth(user),json={'name':'项目助理','scopes':['tasks:read','tasks:write']}).json()
    body={'operations':operations or ['publish','apply','deliver'],'categories':['软件开发'],
          'per_task_cents':20000,'total_cents':30000,'valid_days':7,'acknowledge_responsibility':True}
    r=client.post(f'/api/v1/developer/api-keys/{key["id"]}/mandate',headers=auth(user),json=body)
    assert r.status_code==201,r.text
    return user,key,body


def task(**over):
    return {'title':'开发协作工具','category':'软件开发','budget_cents':18000,'is_remote':True,'ip_assignment':'assign',**over}


def machine(key,idem='one'):
    return {'X-API-Key':key['key'],'Idempotency-Key':idem}


def test_machine_publish_idempotency_and_cumulative_budget(client):
    user,key,_=setup(client)
    r=client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task())
    assert r.status_code==201,r.text
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task()).json()==r.json()
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key,'two'),json=task()).status_code==403
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task(title='改变参数')).status_code==409
    with SessionLocal() as db:
        assert db.get(MachineMandate,key['id']).used_cents==18000
        assert db.query(MachineAction).count()==1
        assert db.query(Task).filter_by(creator_id=user['id']).count()==1


def test_machine_expiry_category_bonus_and_revoke(client):
    user,key,_=setup(client)
    for body in (task(category='保洁'),task(bonus_cents=5000)):
        assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=body).status_code==403
    with SessionLocal() as db:
        row=db.get(MachineMandate,key['id']); row.expires_at=utcnow()-timedelta(seconds=1); db.commit()
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task()).status_code==403
    client.delete(f'/api/v1/developer/api-keys/{key["id"]}',headers=auth(user))
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task()).status_code==403


def test_machine_no_mandate_or_idempotency_no_write_and_no_cross_user_audit(client):
    owner,key,_=setup(client)
    outsider=register(client,'13900880102','其他人')
    for suffix in ('mandate','actions'):
        assert client.get(f'/api/v1/developer/api-keys/{key["id"]}/{suffix}',headers=auth(outsider)).status_code==404
    raw=client.post('/api/v1/developer/api-keys',headers=auth(owner),json={'name':'无授权','scopes':['tasks:write']}).json()
    assert client.post('/api/v1/open/v1/tasks',headers=machine(raw),json=task()).status_code==403
    assert client.post('/api/v1/open/v1/tasks',headers={'X-API-Key':key['key']},json=task()).status_code==400
    assert client.post('/api/v1/wallet/topup',headers=machine(key),json={'amount_cents':100}).status_code==403


def test_machine_cannot_expand_grant_or_operation(client):
    owner,key,body=setup(client,['apply'])
    assert client.post('/api/v1/open/v1/tasks',headers=machine(key),json=task()).status_code==403
    body['total_cents']=100000
    assert client.post(f'/api/v1/developer/api-keys/{key["id"]}/mandate',headers=auth(owner),json=body).status_code==409
    with SessionLocal() as db:
        assert db.get(MachineMandate,key['id']).total_cents==30000


def test_machine_apply_preserves_principal_and_executor_boundary(client):
    owner,key,_=setup(client)
    employer=register(client,'13900880103','发布方')
    t=client.post('/api/v1/tasks',headers=auth(employer),json=task()).json()
    r=client.post(f'/api/v1/open/v1/tasks/{t["id"]}/applications',headers=machine(key,'apply'),json={'message':'授权助理报名'})
    assert r.status_code==201,r.text
    assert r.json()['task_id']==t['id']
    assert client.post(f'/api/v1/open/v1/tasks/{t["id"]}/deliver',headers=machine(key,'deliver'),json={'note':'越权交付'}).status_code==404
    audit=client.get(f'/api/v1/developer/api-keys/{key["id"]}/actions',headers=auth(owner)).json()
    assert audit[0]['principal_id']==owner['id'] and audit[0]['operation']=='apply'
