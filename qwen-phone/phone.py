"""Deploy and operate the device-local Qwen service. Python runs only orchestration."""
import argparse
import hashlib
import getpass
import uuid
import json
import os
from pathlib import Path
import shlex
import secrets
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
ADB = str(ROOT / 'tools/platform-tools/adb')
SERIAL = os.environ.get('QWEN_PHONE_SERIAL')
ADB_PORT = int(os.environ.get('QWEN_ADB_PORT', '5037'))
if not 1024 <= ADB_PORT <= 65535: raise ValueError('Invalid QWEN_ADB_PORT')
REMOTE = '/data/local/tmp/qwen-phone'
RUNTIME = REMOTE + '/llama-b11527'
MODEL = 'Qwen3.5-4B-Q4_0.gguf'
CPU_STRICT = 0
RUNTIME_STATE = ROOT / 'build/active-runtime.json'
_saved_runtime = json.loads(RUNTIME_STATE.read_text()) if RUNTIME_STATE.exists() else {}
MODEL_PORT = int(os.environ.get('QWEN_MODEL_PORT', _saved_runtime.get('model_port', 8080)))
if not 1024 <= MODEL_PORT <= 65535: raise ValueError('Invalid QWEN_MODEL_PORT')
ENV = f'export LD_LIBRARY_PATH={RUNTIME}/lib:/vendor/lib64; export ADSP_LIBRARY_PATH={RUNTIME}/lib; '

def adb(*args, **kw):
    if not SERIAL: raise RuntimeError("Set QWEN_PHONE_SERIAL to the authorized adb device serial")
    return subprocess.run([ADB, '-P', str(ADB_PORT), '-s', SERIAL, *args], check=True, text=True, **kw)

def shell(command, **kw):
    return adb('shell', command, **kw)

def request(path, data=None, port=18180, timeout=300, bearer=None):
    headers = {'Content-Type': 'application/json'}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    key = ROOT / 'tools/inference.key'
    if port == 18180 and key.exists():
        headers['Authorization'] = 'Bearer ' + key.read_text().strip()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/{path}',
        data=json.dumps(data, ensure_ascii=False).encode() if data is not None else None,
        headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def forward():
    adb('forward', 'tcp:18180', f'tcp:{MODEL_PORT}')
    adb('forward', 'tcp:18090', 'tcp:8090')

def stop_one(name):
    # Check the saved PID's command line before terminating a previously started service.
    pattern = 'llama-server' if name == 'server' else 'PhoneAgent'
    shell(f'if [ -f {REMOTE}/{name}.pid ]; then p=$(cat {REMOTE}/{name}.pid); '
          f'case "$p" in ""|*[!0-9]*) exit 1;; esac; '
          f'if [ -r /proc/$p/cmdline ] && tr "\\000" " " < /proc/$p/cmdline 2>/dev/null | grep -q {pattern}; then kill "$p"; fi; fi')

def staging_env():
    lock = json.loads((ROOT / 'native/runtime-lock.json').read_text())
    for name, expected in lock['libraries'].items():
        actual = shell(f'sha256sum {RUNTIME}/lib/{name}', capture_output=True).stdout.split()[0]
        if actual != expected:
            raise RuntimeError('Staging ABI mismatch: ' + name)
    native = ROOT / 'build/map-staging.so'
    expected = hashlib.sha256(native.read_bytes()).hexdigest()
    actual = shell(f'sha256sum {REMOTE}/map-staging.so', capture_output=True).stdout.split()[0]
    if actual != expected: raise RuntimeError('Run build-native.sh before starting staging mode')
    return ENV + f'export LD_PRELOAD={REMOTE}/map-staging.so; export GGML_HEXAGON_OPFUSION=0; export GGML_HEXAGON_MBUF=64,128; export GGML_HEXAGON_VMEM=1536; '

def start(backend, threads=5, layers=None, vision=False):
    launch_env = staging_env() if backend == 'htp-staging' else ENV
    if backend == 'htp-staging': layers = 99
    if vision:
        expected='cd88edcf8d031894960bb0c9c5b9b7e1fea6ebee02b9f7ce925a00d12891f864'
        actual=shell(f'sha256sum {REMOTE}/mmproj-Qwen3.5-4B-F16.gguf',capture_output=True).stdout.split()[0]
        if actual!=expected: raise RuntimeError('Vision projector checksum mismatch')
    stop_one('server')
    key = ROOT / 'tools/inference.key'
    if not key.exists():
        key.write_text(secrets.token_urlsafe(32) + '\n')
    key.chmod(0o600)
    adb('push', str(key), REMOTE + '/inference.key', stdout=subprocess.DEVNULL)
    shell(f'chmod 600 {REMOTE}/inference.key')
    device, ngl = ('none', 0) if backend == 'cpu' else ('HTP0', 28 if layers is None else layers)
    args = [RUNTIME + '/bin/llama-server', '-m', REMOTE + '/' + MODEL,
            '--alias', 'qwen3.5-4b', '--host', '127.0.0.1', '--port', str(MODEL_PORT),
            '--api-key-file', REMOTE + '/inference.key',
            '-c', '4096', '--parallel', '1', '-b', '256', '-ub', '64',
            '-t', str(threads), '-tb', '5', '--cpu-mask', 'f8', '--cpu-strict', str(CPU_STRICT),
            '--device', device, '-ngl', str(ngl), '--fit', 'off', '--jinja', '--reasoning', 'auto', '--reasoning-budget', '128', '--slots', '--cache-ram', '0', '--no-context-shift', '-fa', 'on']
    if vision: args += ['--mmproj',REMOTE+'/mmproj-Qwen3.5-4B-F16.gguf','--no-mmproj-offload','--image-max-tokens','1024']
    shell(launch_env + f'nohup {shlex.join(args)} > {REMOTE}/server.log 2>&1 < /dev/null & echo $! > {REMOTE}/server.pid')
    forward()
    for _ in range(180):
        try:
            if request('health', timeout=2).get('status') == 'ok':
                print(json.dumps({'server': 'ready', 'backend_requested': backend, 'threads': threads, 'gpu_layers': ngl}))
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        shell(f'tail -80 {REMOTE}/server.log')
        raise RuntimeError('Server did not become ready; inspect server.log')
    stop_one('agent')
    shell(f'QWEN_MODEL_PORT={MODEL_PORT} QWEN_VISION={1 if vision else 0} CLASSPATH={REMOTE}/agent.jar nohup app_process /system/bin PhoneAgent > {REMOTE}/agent.log 2>&1 < /dev/null & echo $! > {REMOTE}/agent.pid')
    for _ in range(10):
        try:
            print(request('health', port=18090, timeout=2))
            RUNTIME_STATE.parent.mkdir(parents=True, exist_ok=True)
            RUNTIME_STATE.write_text(json.dumps({'model_port': MODEL_PORT}))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError('Agent failed to start')

def ask(prompt, thinking=False, skill='assistant'):
    forward()
    health = request('health', port=18090)
    if not health.get('vault_initialized'):
        raise RuntimeError('请先在 http://127.0.0.1:18090 创建资料库口令')
    auth = request('unlock', {'password': getpass.getpass('资料库口令：'), 'create': False}, port=18090)
    bearer = auth['token']
    def agent(path, body=None):
        return request(path, body, port=18090, bearer=bearer)
    try:
        job = agent('jobs', {'prompt': prompt, 'session': str(uuid.uuid4()), 'thinking': thinking, 'skill': skill})
        approved = set()
        while True:
            state = agent('jobs/' + job['id'])
            approval = state.get('approval')
            if approval and approval['id'] not in approved:
                print(('保存笔记：'+approval['name']+'\n'+approval['content']) if approval.get('kind')=='write_note' else '发送到 Bing 的查询：'+approval['query'])
                allow = input('允许本次操作？输入 yes 允许：').strip().lower() == 'yes'
                agent('jobs/' + job['id'] + '/approve', {'id': approval['id'], 'allow': allow})
                approved.add(approval['id'])
            if state['status'] in ('done', 'error', 'cancelled'):
                print(json.dumps(state['result'], ensure_ascii=False, indent=2))
                if state['status'] in ('error','cancelled'): raise RuntimeError('Agent task failed')
                return
            time.sleep(1)
    finally:
        agent('lock', {})

def deploy():
    model = ROOT / 'models' / MODEL
    with model.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    expected = '298fcb5fe7a77ccc79745ae24751560c5ac56874caff4bb39b1f2055bd72b8bb'
    if digest != expected:
        raise ValueError('Local model checksum mismatch')
    adb('push', '-Z', str(model), REMOTE + '/' + MODEL)
    result = shell(f'sha256sum {REMOTE}/{MODEL}', capture_output=True).stdout
    if result.split()[0] != expected:
        raise ValueError('Device model checksum mismatch')
    (ROOT / 'reports/device-model-sha256.txt').write_text(result)
    print(result)

def bench(backend, threads, layers, label, repetitions):
    launch_env = staging_env() if backend == 'htp-staging' else ENV
    if backend == 'htp-staging': layers = 99
    stop_one('server')
    args = [RUNTIME + '/bin/llama-bench', '-m', REMOTE + '/' + MODEL,
        '-p', '128', '-n', '32', '-r', str(repetitions), '-b', '256', '-ub', '64',
        '-t', str(threads), '-C', 'f8', '--cpu-strict', str(CPU_STRICT), '-fa', 'on',
        '-ngl', str(0 if backend == 'cpu' else layers),
        '--device', 'none' if backend == 'cpu' else 'HTP0', '-o', 'json']
    target = ROOT / 'reports' / label
    pre = shell('dumpsys battery; head -5 /proc/meminfo', capture_output=True).stdout
    target.with_suffix('.before.txt').write_text(pre)
    with target.with_suffix('.json').open('w') as out, target.with_suffix('.log').open('w') as err:
        result = subprocess.run([ADB, '-s', SERIAL, 'shell', launch_env + '/system/bin/time -v timeout 480 ' + shlex.join(args)], stdout=out, stderr=err, timeout=500)
    target.with_suffix('.after.txt').write_text(shell('dumpsys battery; head -5 /proc/meminfo', capture_output=True).stdout)
    print(f'{label}: exit={result.returncode}; {target}.json')
    if result.returncode:
        print(target.with_suffix('.log').read_text()[-6000:])
        raise RuntimeError(f'Benchmark failed with exit {result.returncode}: {label}')
    else:
        print(target.with_suffix('.json').read_text())

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['deploy', 'start', 'stop', 'status', 'ask', 'bench', 'logs'])
    parser.add_argument('--backend', choices=['cpu', 'htp', 'htp-staging'], default='htp')
    parser.add_argument('--threads', type=int, default=5)
    parser.add_argument('--cpu-strict', type=int, choices=[0, 1], default=0)
    parser.add_argument('--layers', type=int, default=28)
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--label', default='benchmark')
    parser.add_argument('--vision',action='store_true',help='Load the verified local vision projector')
    parser.add_argument('--thinking', action='store_true')
    parser.add_argument('--skill', choices=['assistant', 'offline', 'research'], default='assistant')
    parser.add_argument('--prompt', default='请查询这台手机的型号和当前时间。')
    args = parser.parse_args()
    CPU_STRICT = args.cpu_strict
    if args.action == 'deploy': deploy()
    elif args.action == 'start': start(args.backend, args.threads, args.layers, args.vision)
    elif args.action == 'stop': stop_one('server'); stop_one('agent')
    elif args.action == 'bench':
        if not args.label.replace('-', '').replace('_', '').isalnum(): raise ValueError('Invalid label')
        bench(args.backend, args.threads, args.layers, args.label, args.repetitions)
    elif args.action == 'ask':
        ask(args.prompt, args.thinking, args.skill)
    elif args.action == 'status':
        forward()
        print(request('health')); print(request('health', port=18090))
    elif args.action == 'logs': shell(f'tail -80 {REMOTE}/server.log; tail -20 {REMOTE}/agent.log')
