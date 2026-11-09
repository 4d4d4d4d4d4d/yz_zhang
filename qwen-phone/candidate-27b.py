"""Verify/deploy the isolated 27B candidate; never replaces the production model.
Usage: python candidate-27b.py verify|deploy|preflight
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
import phone
ROOT=Path(__file__).resolve().parent
META=json.loads((ROOT/'reports/model-27b-candidates.json').read_text())
FILES={'Qwen3.5-27B-UD-IQ2_XXS.gguf':'Qwen3.5-27B-UD-IQ2_XXS.gguf','mmproj-F16.gguf':'mmproj-Qwen3.5-27B-F16.gguf'}
REPORT=ROOT/'reports/model-27b-readiness.json'
def verify():
 results=[]
 for remote,local in FILES.items():
  expected=next(x for x in META['siblings'] if x['rfilename']==remote)
  path=ROOT/'models'/local
  if not path.exists() or path.stat().st_size!=expected['size']:raise RuntimeError('Download incomplete: '+local)
  h=hashlib.sha256()
  with path.open('rb') as source:
   for block in iter(lambda:source.read(8*1024*1024),b''):h.update(block)
  if h.hexdigest()!=expected['lfs']['sha256']:raise RuntimeError('SHA256 mismatch: '+local)
  results.append({'file':local,'size':path.stat().st_size,'sha256':h.hexdigest()})
 return results
def preflight():
 # A conservative residency estimate, not a claim about exact mmap/Android reclaim behavior.
 raw=phone.shell('cat /proc/meminfo',capture_output=True).stdout
 memory={line.split(':')[0]:int(line.split()[1])*1024 for line in raw.splitlines() if line.split()[1].isdigit()}
 weights=sum(next(x['size'] for x in META['siblings'] if x['rfilename']==name) for name in FILES)
 required=weights+2*1024**3
 result={'candidate':'Qwen3.5-27B-UD-IQ2_XXS','vision':'F16','repository':META['repository'],'revision':META['sha'],'memory_available_bytes':memory['MemAvailable'],'memory_total_bytes':memory['MemTotal'],'weights_bytes':weights,'conservative_required_available_bytes':required,'memory_gate_passed':memory['MemAvailable']>=required,'note':'Current services remain running. This gate is conservative; a pass does not prove load or vision accuracy. IQ2 CPU trial only; no APK/default-model switch.'}
 REPORT.write_text(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','preflight','deploy']);a=p.parse_args()
 if a.action=='preflight':print(json.dumps(preflight(),indent=2))
 else:
  verified=verify();print(json.dumps(verified,indent=2))
  if a.action=='deploy':
   state=preflight()
   if not state['memory_gate_passed']:raise SystemExit('Memory gate failed; production service left running. See reports/model-27b-readiness.json')
   folder=phone.REMOTE+'/candidate-27b';phone.shell('mkdir -p '+folder)
   for f in verified:
    target=folder+'/'+f['file'];phone.adb('push',str(ROOT/'models'/f['file']),target+'.partial')
    actual=phone.shell('sha256sum '+target+'.partial',capture_output=True).stdout.split()[0]
    if actual!=f['sha256']:raise RuntimeError('Device checksum mismatch')
    phone.shell('mv '+target+'.partial '+target)
