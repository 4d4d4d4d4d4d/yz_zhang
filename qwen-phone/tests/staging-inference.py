"""Public synthetic prompts; bypasses and never unlocks the private agent vault."""
import sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import phone
cases=[('literal','请只回复字符串：POOL-OK-927','POOL-OK-927'),('math','17 乘以 23 等于多少？只回答结果。','391'),('long-context','本次测试的代号是 ORBIT-93。\n'+'这是用于验证模型上下文处理的公开测试资料。'*240+'\n请仅回答开头的测试代号。','ORBIT-93'),('fresh-request','请只回复字符串：NEW-SESSION-641','NEW-SESSION-641')]
results=[]
(phone.ROOT/'reports/npu-fix').mkdir(parents=True,exist_ok=True)
for label,prompt,expected in cases:
 b={'model':'qwen3.5-4b','messages':[{'role':'user','content':prompt}],'temperature':0,'max_tokens':48,'cache_prompt':False,'chat_template_kwargs':{'enable_thinking':False}}
 templ=phone.request('apply-template',b)['prompt'];tokens=len(phone.request('tokenize',{'content':templ})['tokens']);start=time.monotonic()
 r=phone.request('v1/chat/completions',b);answer=r['choices'][0]['message']['content'];ok=expected in answer
 results.append({'case':label,'tokens':tokens,'elapsed':time.monotonic()-start,'ok':ok,'response':r})
 (phone.ROOT/'reports/npu-fix/staging-inference.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(label,tokens,ok,answer,flush=True);assert ok,(label,answer)
print('STAGING_INFERENCE_OK',flush=True)
