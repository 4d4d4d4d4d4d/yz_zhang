"""Run inside the API container against private staging only; creates test fixtures.

Refuses non-test or non-PostgreSQL environments. Uses seed demo accounts, never
prints tokens/keys. Funding is a simulated fixture via the internal wallet service.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import httpx
from app.core.db import SessionLocal
from app.modules.wallet import service as wallet

assert os.environ.get('PLATFORM_ENV') == 'test', 'TEST ENVIRONMENT ONLY'
assert os.environ.get('PLATFORM_DATABASE_URL','').startswith('postgresql'), 'Postgres required'
base='http://127.0.0.1:8000/api/v1'
tag=uuid.uuid4().hex[:8]
client=httpx.Client(timeout=30)


def call(method,path,body=None,headers=None,status=200):
    r=client.request(method,base+path,json=body,headers=headers)
    assert r.status_code==status,(path,r.status_code,r.text)
    return r.json()


def login(phone):
    d=call('POST','/auth/login',{'phone':phone,'password':'pass123456'})
    return d['user'],{'Authorization':'Bearer '+d['token']}


a,ha=login('13900010001');b,hb=login('13900010003')
key=call('POST','/developer/api-keys',{'name':'PG smoke '+tag,'scopes':['tasks:read','tasks:write']},ha,201)
kp=f'/developer/api-keys/{key["id"]}'
try:
    call('POST',kp+'/mandate',{'operations':['publish'],'categories':['软件开发'],
        'per_task_cents':20000,'total_cents':30000,'valid_days':1,'acknowledge_responsibility':True},ha,201)
    payload={'title':'机器授权并发测试 '+tag,'category':'软件开发','budget_cents':18000,'is_remote':True,'ip_assignment':'assign'}
    def publish(i):
        return client.post(base+'/open/v1/tasks',json=payload,headers={'X-API-Key':key['key'],'Idempotency-Key':tag+str(i)})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(publish,[1,2]))
    assert sorted(r.status_code for r in responses)==[201,403],[(r.status_code,r.text) for r in responses]
    winner=next(i+1 for i,r in enumerate(responses) if r.status_code==201)
    assert publish(winner).json()==responses[winner-1].json()
    assert call('GET',kp+'/mandate',headers=ha)['used_cents']==18000
    assert len(call('GET',kp+'/actions',headers=ha))==1
    print('PASS PostgreSQL concurrent machine limit + idempotency')
finally:
    call('DELETE',kp,headers=ha)

ver=call('GET','/ventures/risk-disclosure')['version']
v=call('POST','/ventures',{'name':'共同确认联调 '+tag,'purpose':'模拟资金验收','risk_disclosure_version':ver},ha,201)
vp=f'/ventures/{v["id"]}'
call('POST',vp+'/members',{'risk_disclosure_version':ver},hb,403)
call('POST',vp+'/invitations',{'user_id':b['id']},ha,201)
call('POST',vp+'/members',{'risk_disclosure_version':ver},hb,201)
org=call('POST',vp+'/organization-records',{'entity_type':'project_cooperation',
    'jurisdiction':'测试法域（非正式登记）','registered_name':'演示协作项目 '+tag,
    'representative_user_id':a['id'],'governance_basis':'仅用于模拟环境测试的成员约定，不是正式公司章程',
    'document_references':['测试约定 v1'],'rights':[],
    'acknowledge_record_only':True,'acknowledge_member_visibility':True},ha,201)
assert org['verification_status']=='declared_unverified'
c=call('POST',vp+'/contributions',{'kind':'time','description':'模拟原型交付'},ha,201)
call('POST',vp+f'/contributions/{c["id"]}/confirm',{'accept':True,'valued_cents':10000,'note':'模拟核验'},hb)
with SessionLocal() as db:
    wallet.topup(db,v['id'],20000);db.commit()
p=call('POST',vp+'/payout-proposals',{'amount_cents':10000,'memo':'仅模拟资金'},ha,201)
body={'amount_cents':p['amount_cents'],'memo':p['memo'],'proposal_id':p['id']}
call('POST',vp+'/distributions',body,ha,403)
call('POST',vp+f'/payout-proposals/{p["id"]}/vote',{'approve':True},hb)
with ThreadPoolExecutor(max_workers=2) as pool:
    payouts=list(pool.map(lambda _:call('POST',vp+'/distributions',body,ha,201),[1,2]))
assert payouts[0]==payouts[1]
assert len(call('GET',vp+'/distributions',headers=ha))==1
assert call('GET',vp,headers=ha)['realized_funds_cents']==10000
print('PASS invitations + declared organization records + unanimous payout + concurrent replay')
print('Fixture venture_id=',v['id'],'proposal_id=',p['id'])
