"""Loopback-only synthetic screenshot test; model runs on the connected phone.
No credentials in browser, no real bookings, no personal screenshots.
"""
import base64,json,sys,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phone
OUT=phone.ROOT/'reports/travel-acceptance'
FIXTURE='''<!doctype html><meta charset="utf-8"><title>订票视觉验收 · 模拟页面</title><style>body{background:#101923;color:#e7edf4;font:20px system-ui;margin:0;padding:20px}main{max-width:640px;margin:auto}small{color:#a8bbc9}h1{font-size:32px}.card{background:#1d2c3a;border-radius:20px;padding:16px;margin:12px 0}button{font:inherit;border:0;border-radius:12px;padding:12px;background:#4ce4c1;color:#101923}button:disabled{background:#45515e;color:#b8c0c8}.row{display:flex;gap:20px;margin:16px 0}.price{color:#4ce4c1;font-size:32px}</style><main><small>工程模拟 · 非真实票务 / 不会产生订单</small><h1>西山岛 · 湖畔观景园</h1><p>成人票 · 请先选择出行日期</p><div class="card"><small>选择日期</small><div class="row"><button disabled>10月24日<br>已售罄</button><button>10月25日<br>可预约</button></div><p>当前未选择日期</p></div><div class="card"><p>成人单价 <b class="price">¥68</b></p><p>人数 2位成人</p><p>合计 <b>¥136</b></p><small>开放时间 09:00–17:00 · 16:30停止入园</small></div><div class="row"><button>返回</button><button disabled>下一步</button></div></main>'''
FORM='''<!doctype html><meta charset="utf-8"><title>手机本地视觉测试</title><h1>本地截图分析测试</h1><p>只提交工程模拟截图，推理由手机执行。</p><textarea aria-label="截图数据" rows="3"></textarea><button id="run">分析截图</button><pre id="result">等待截图</pre><script>run.onclick=async()=>{run.disabled=true;result.textContent='手机正在分析';try{const image=document.querySelector('textarea').value;const r=await fetch('/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image})});result.textContent=JSON.stringify(await r.json(),null,2)}catch(e){result.textContent=String(e)}finally{run.disabled=false}};</script>'''
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def send(self,status,data,kind='text/html; charset=utf-8'):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data.encode())
 def do_GET(self):
  if self.headers.get('Host')!='127.0.0.1:18092':return self.send(403,'forbidden')
  self.send(200,FIXTURE if self.path=='/fixture' else FORM)
 def do_POST(self):
  if self.path!='/analyze' or self.headers.get('Origin')!='http://127.0.0.1:18092' or self.headers.get('Host')!='127.0.0.1:18092':return self.send(403,'forbidden')
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<1800000:raise ValueError('image size')
   image=json.loads(self.rfile.read(size))['image']
   if not image.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):raise ValueError('PNG/JPEG required')
   raw=base64.b64decode(image.split(',',1)[1],validate=True)
   ext='png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if raw.startswith(b'\xff\xd8\xff') else None
   if ext is None:raise ValueError('invalid image')
   image='data:image/'+('jpeg' if ext=='jpg' else 'png')+';base64,'+base64.b64encode(raw).decode()
   OUT.mkdir(exist_ok=True);(OUT/('booking-fixture.'+ext)).write_bytes(raw)
   prompt='仅按图用120字以内回答：逐字抄出日期选择状态那一行；24日和25日是否有票；单价、人数、合计；下一步按钮是否可用。可预约不等于已选择，不能仅凭颜色推断已选择或已点击。无法确定按钮可点击就写不确定并停止。用户必须24日出行，不得替用户改日期或宣称已执行。'
   begin=time.monotonic()
   r=phone.request('v1/chat/completions',{'model':'qwen3.5-4b','messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':image}}]}],'max_tokens':600,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}},timeout=240)
   result={'execution':'phone-local-qwen3.5-4b-htp28-vision-cpu','source':'synthetic-browser-screenshot-not-phone-capture','elapsed_seconds':round(time.monotonic()-begin,2),'prompt':prompt,'answer':r['choices'][0]['message']['content'],'finish_reason':r['choices'][0]['finish_reason'],'usage':r.get('usage')}
   (OUT/'vision-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));self.send(200,json.dumps(result,ensure_ascii=False),'application/json')
  except Exception as e:self.send(500,json.dumps({'error':str(e)},ensure_ascii=False),'application/json')
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',18092),Handler).serve_forever()
