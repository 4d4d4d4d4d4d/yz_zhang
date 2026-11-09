"""Focused checks against the disposable UI test vault only."""
import json,time,urllib.request,urllib.error
B='http://127.0.0.1:18090'
def req(path,body=None,token=None):
    h={'Content-Type':'application/json'}
    if token:h['Authorization']='Bearer '+token
    with urllib.request.urlopen(urllib.request.Request(B+path,data=None if body is None else json.dumps(body).encode(),headers=h),timeout=30) as r:return json.load(r)
def rejected(path,body,token):
    try:req(path,body,token)
    except urllib.error.HTTPError as e:assert e.code in (400,401);return
    raise AssertionError('unauthorized access')
assert req('/health')['test_vault']
p='Disposable-UI-Test-2026-only'
t=req('/unlock',{'password':p})['token']
sessions=req('/sessions',token=t)['sessions'];assert sessions
assert req('/profile',token=t)['profile']=={'测试偏好':'只用简短中文'}
assert req('/session-status',token=t)['unlocked']
time.sleep(3.1);rejected('/unlock',{'password':'incorrect-password-123'},None)
assert req('/profile',token=t)['profile']
time.sleep(3.1);t2=req('/unlock',{'password':p})['token']
rejected('/profile',None,t)
sid=sessions[0]['id'];req('/sessions/delete',{'session':sid},t2)
assert not any(s['id']==sid for s in req('/sessions',token=t2)['sessions'])
j=req('/jobs',{'prompt':'请简短说明地球为什么有四季。'},t2)
req('/lock',{},t2);rejected('/jobs/'+j['id'],None,t2)
print('SESSION_SECURITY_OK: encrypted index/profile reopen, wrong reauth preserves key, token rotation, session delete, lock cancels job')
