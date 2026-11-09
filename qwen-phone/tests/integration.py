"""Device integration against a server started with --test-vault; never uses the user's vault."""
import json, secrets, time, urllib.request, urllib.error, uuid
from pathlib import Path
BASE='http://127.0.0.1:18090'
token=''
report=[]
def call(path,body=None,extra=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    if extra:headers.update(extra)
    req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
def expect_error(path,body,code,extra=None):
    try:call(path,body,extra)
    except urllib.error.HTTPError as e:assert e.code==code,(e.code,e.read());return
    raise AssertionError('unexpected success')
def run(prompt,session=None,thinking=False,compress=False,allow=False,skill='assistant'):
    j=call('/jobs',{'prompt':prompt,'session':session or str(uuid.uuid4()),'thinking':thinking,'compress':compress,'skill':skill})
    begin=time.monotonic();seen=set()
    while time.monotonic()-begin<400:
        s=call('/jobs/'+j['id'])
        if s['approval'] and s['approval']['id'] not in seen:
            seen.add(s['approval']['id']);print('approval kind:',s['approval'].get('kind','web_search'),flush=True)
            call('/jobs/'+j['id']+'/approve',{'id':s['approval']['id'],'allow':allow or s['approval'].get('kind')=='write_note'})
        if s['status'] in ('done','error'):
            report.append({'prompt':prompt,'status':s['status'],'events':s['events'],'result':s['result']})
            Path('qwen-phone/reports/v2/integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(prompt, s['status'], json.dumps(s['result'],ensure_ascii=False),flush=True)
            assert s['status']=='done',s
            return s['result'],s['events']
        time.sleep(.75)
    raise TimeoutError(prompt)
health=call('/health');assert health['version']==2 and health['test_vault'] and not health['vault_initialized'], 'requires a fresh --test-vault server'
expect_error('/profile',None,401)
expect_error('/unlock',{'password':'irrelevant-password'},403,{'Origin':'https://evil.example'})
password=secrets.token_urlsafe(24)
token=call('/unlock',{'password':password,'create':True})['token']
call('/profile',{'profile':{'测试偏好':'请使用简洁中文'}})
assert call('/profile')['profile']['测试偏好']=='请使用简洁中文'
sid=str(uuid.uuid4())
r,_=run('请调用工具查询这台手机的型号和当前时间。',sid)
assert {'device_status','get_time'} <= {t['name'] for t in r['tools']}
r,_=run('请把内容 test-marker-7362 保存到名为 integration 的笔记，然后读取该笔记确认。',sid)
assert 'test-marker-7362' in json.dumps(r,ensure_ascii=False)
r,_=run('17 乘以 23 等于多少？',thinking=True,skill='offline')
assert '391' in r['answer'] and r['reasoning']
r,_=run('请检索 Android NEON 官方文档。',allow=True,skill='research')
assert any(t['name']=='web_search' and t['result'].get('results') for t in r['tools'])
r,_=run('请检索 Android SQLite 官方文档。',allow=False,skill='research')
assert any(t['name']=='web_search' and 'error' in t['result'] for t in r['tools'])
r,_=run('刚才保存的测试笔记叫什么？请根据对话历史回答。',sid,compress=True)
assert 'integration' in r['answer']
call('/sessions/delete',{'session':sid})
call('/profile',{'profile':{}});assert call('/profile')['profile']=={}
call('/lock',{});expect_error('/profile',None,401)
token=call('/unlock',{'password':password,'create':False})['token']
assert call('/profile')['profile']=={}
call('/lock',{})
print('INTEGRATION_OK: auth, origin, profile, tools, notes, reasoning, search allow/deny, compression, delete, lock/reopen',flush=True)
