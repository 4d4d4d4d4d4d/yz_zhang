"""macOS local Web + private SSH tunnel, supervised by the user's launchd.
Run with the repository virtualenv Python: deploy/local-preview.py start|stop|status.
"""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('action', choices=['start', 'stop', 'status', 'chain-start', 'chain-stop'])
args = parser.parse_args()
node = shutil.which('node')
if not node:
    raise SystemExit('Node.js is required')
agents = Path.home() / 'Library/LaunchAgents'
logs = Path.home() / 'Library/Logs/OPC'
agents.mkdir(parents=True, exist_ok=True)
logs.mkdir(parents=True, exist_ok=True)
domain = f'gui/{os.getuid()}'
configs = {
    'local.opc.staging-tunnel': ['/usr/bin/ssh', '-N', '-i', str(Path.home()/'.ssh/id_ed25519'),
        '-p', '22', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3',
        '-L', '127.0.0.1:18080:127.0.0.1:18080', 'root@192.227.211.5'],
    'local.opc.web-preview': [node, str(root/'node_modules/vite/bin/vite.js'),
        '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
}
chain_label = 'local.opc.chain-demo'
if args.action in ('chain-start', 'chain-stop', 'status'):
    if args.action != 'status':
        configs = {}
    configs[chain_label] = [str(root/'chain/node_modules/node/bin/node'), str(root/'chain/scripts/demo.mjs')]
action = {'chain-start': 'start', 'chain-stop': 'stop'}.get(args.action, args.action)
for label, command in configs.items():
    path = agents / (label + '.plist')
    loaded = subprocess.run(['/bin/launchctl', 'print', f'{domain}/{label}'], capture_output=True, text=True)
    if action == 'status':
        print(label, 'loaded' if loaded.returncode == 0 else 'stopped')
        continue
    if action == 'stop':
        if loaded.returncode == 0:
            subprocess.run(['/bin/launchctl', 'bootout', f'{domain}/{label}'], check=True)
        path.unlink(missing_ok=True)
        print(label, 'stopped')
        continue
    data = {'Label': label, 'ProgramArguments': command,
        'WorkingDirectory': str(root/'chain' if label == chain_label else root/'web' if label.endswith('web-preview') else root),
        'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10,
        'StandardOutPath': str(logs/(label+'.log')), 'StandardErrorPath': str(logs/(label+'.error.log')),
        'EnvironmentVariables': {'PATH': str(Path(node).parent)+':/usr/bin:/bin:/usr/sbin:/sbin'}}
    if loaded.returncode == 0 and path.exists() and plistlib.loads(path.read_bytes()) == data:
        print(label, 'already loaded')
        continue
    if loaded.returncode == 0:
        subprocess.run(['/bin/launchctl', 'bootout', f'{domain}/{label}'], check=True)
    path.write_bytes(plistlib.dumps(data))
    path.chmod(0o600)
    subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(path)], check=True)
    print(label, 'started')
