import json,time,uuid,urllib.request
B='http://127.0.0.1:18090';token=''
def req(path,body=None):
    h={'Content-Type':'application/json','Authorization':'Bearer '+token}
    with urllib.request.urlopen(urllib.request.Request(B+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode(),headers=h),timeout=30) as r:return json.load(r)
assert req('/health')['test_vault']
token=req('/unlock',{'password':'Disposable-UI-Test-2026-only'})['token'];sid=str(uuid.uuid4())
results=[]
try:
    for p in ['此对话的测试代号是 ORBIT-73。请只回复收到，不要写笔记。','请先调用工具查询当前时间，再调用 compress_context 压缩历史，最后告诉我测试代号与刚查询的时间。']:
        j=req('/jobs',{'prompt':p,'session':sid,'skill':'offline'})
        end=time.monotonic()+240
        while time.monotonic()<end:
            s=req('/jobs/'+j['id'])
            if s['status'] in ('done','error'):break
            time.sleep(.75)
        assert s['status']=='done',s
        results.append(s);print(json.dumps(s['result'],ensure_ascii=False),flush=True)
    r=results[-1]['result'];assert 'ORBIT-73' in r['answer'];assert {'get_time','compress_context'} <= {t['name'] for t in r['tools']}
    open('qwen-phone/reports/v2/compression-tools.json','w').write(json.dumps(results,ensure_ascii=False,indent=2))
    print('COMPRESSION_TOOL_DIALOGUE_OK',flush=True)
finally:req('/lock',{})
