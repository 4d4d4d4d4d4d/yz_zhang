"""Bounded experimental CPU trial, independent of APK and default model files."""
import base64,json,shlex,sys,time,threading,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import phone
ROOT=phone.ROOT; REMOTE=phone.REMOTE+'/candidate-27b'; OUT=ROOT/'reports/model-27b-trial.json'
report={'model':'Qwen3.5-27B-UD-IQ2_XXS','backend':'CPU','context':2048,'experimental_below_conservative_memory_gate':True,'samples':[],'tests':[]}
stop=threading.Event();memory_abort=threading.Event()
def shell(s):return phone.shell(s,capture_output=True).stdout.strip()
def checkpoint():OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
def shutdown():
 shell(f'if [ -f {REMOTE}/trial.pid ]; then p=$(cat {REMOTE}/trial.pid); case "$p" in ""|*[!0-9]*) exit 1;; esac; if tr "\\000" " " < /proc/$p/cmdline 2>/dev/null | grep -q "{REMOTE}/model.gguf"; then kill "$p"; fi; fi')
def monitor():
 while not stop.wait(5):
  try:
   raw=shell("awk '/MemAvailable:/{print $2}' /proc/meminfo");available=int(raw)*1024
   report['samples'].append({'time':time.time(),'available_bytes':available})
   if available<256*1024*1024:memory_abort.set();shutdown();return
  except Exception:return
key=(ROOT/'tools/inference.key').read_text().strip()
def req(path,body=None,timeout=10):
 headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
 r=urllib.request.Request('http://127.0.0.1:18186/'+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 with urllib.request.urlopen(r,timeout=timeout) as response:return json.load(response)
def infer(name,content):
 report['active_test']=name;checkpoint();start=time.monotonic();r=req('v1/chat/completions',{'model':'qwen3.5-27b-trial','messages':[{'role':'user','content':content}],'temperature':0,'max_tokens':128,'chat_template_kwargs':{'enable_thinking':False}},timeout=180)
 report['tests'].append({'name':name,'elapsed_seconds':round(time.monotonic()-start,2),'response':r});checkpoint()
try:
 report['memory_before']=shell('head -5 /proc/meminfo');checkpoint()
 args=[phone.RUNTIME+'/bin/llama-server','-m',REMOTE+'/model.gguf','--mmproj',REMOTE+'/mmproj.gguf','--no-mmproj-offload','--image-max-tokens','1024','--alias','qwen3.5-27b-trial','--host','127.0.0.1','--port','8086','--api-key-file',phone.REMOTE+'/inference.key','-c','2048','--parallel','1','-b','64','-ub','32','-t','4','-tb','4','--device','none','-ngl','0','--fit','off','--jinja','--cache-ram','0','--no-warmup']
 inner=f'echo $$ > {REMOTE}/trial.pid; '+phone.ENV+'exec '+shlex.join(args)
 shell(f'nohup timeout -s KILL 360 sh -c {shlex.quote(inner)} > {REMOTE}/trial.log 2>&1 < /dev/null &')
 phone.adb('forward','tcp:18186','tcp:8086',stdout=__import__('subprocess').DEVNULL)
 watcher=threading.Thread(target=monitor,daemon=True);watcher.start();start=time.monotonic()
 while time.monotonic()-start<120:
  if memory_abort.is_set():raise RuntimeError('Stopped: available memory below 256MiB')
  try:
   if req('health',timeout=2).get('status')=='ok':break
  except Exception:pass
  time.sleep(2)
 else:raise TimeoutError('Model did not become healthy within 120s')
 report['load_seconds']=round(time.monotonic()-start,2);checkpoint()
 infer('text','只回答 2+3 的数字结果。')
 image=base64.b64encode((ROOT/'reports/travel-acceptance/booking-fixture.jpg').read_bytes()).decode()
 infer('booking-ui',[{'type':'text','text':'只按图回答：当前选了日期吗？24日和25日状态？单价、人数、合计？下一步能否点击？用户必须24日出行。可预约不等于已选；无法确定则停止。80字以内。'},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+image}}])
 report['status']='completed'
except Exception as e:report.update(status='failed',error=type(e).__name__+': '+str(e))
finally:
 stop.set()
 try:
  shutdown();time.sleep(3)
  shell(f'if [ -f {REMOTE}/trial.pid ]; then p=$(cat {REMOTE}/trial.pid); case "$p" in ""|*[!0-9]*) exit 1;; esac; if tr "\\000" " " < /proc/$p/cmdline 2>/dev/null | grep -q "{REMOTE}/model.gguf"; then kill -9 "$p"; fi; fi')
 except Exception:pass
 try:
  report['memory_after']=shell('head -5 /proc/meminfo')
  (ROOT/'reports/model-27b-trial.log').write_text(shell(f'cat {REMOTE}/trial.log'))
 except Exception:pass
 checkpoint();print(json.dumps({k:v for k,v in report.items() if k not in ('samples','tests')},ensure_ascii=False,indent=2))
