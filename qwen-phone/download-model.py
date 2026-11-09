"""Download pinned model in validated ranges; verify entire file before use."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time
import requests

ROOT = Path(__file__).resolve().parent
META = json.loads((ROOT / 'reports/model-api.json').read_text())
NAME = 'Qwen3.5-4B-Q4_0.gguf'
FILE = next(x for x in META['siblings'] if x['rfilename'] == NAME)
SIZE = FILE['size']
CHUNK = 32 * 1024 * 1024
URL = f'https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/{META["sha"]}/{NAME}'
PROXIES = {'http': 'http://127.0.0.1:7897', 'https': 'http://127.0.0.1:7897'}
PARTS = ROOT / 'models/parts'
PARTS.mkdir(parents=True, exist_ok=True)

def fetch(i):
    start, end = i * CHUNK, min(SIZE, (i + 1) * CHUNK) - 1
    path = PARTS / f'{i:04d}'
    if path.exists() and path.stat().st_size == end - start + 1:
        return path
    for attempt in range(20):
        try:
            temp = path.with_suffix('.tmp')
            offset = temp.stat().st_size if temp.exists() else 0
            if offset == end - start + 1:
                temp.replace(path)
                return path
            current = start + offset
            with requests.get(URL + f'?download=true&part={i}&offset={offset}', headers={'Range': f'bytes={current}-{end}'},
                              proxies=PROXIES, stream=True, timeout=(20, 90)) as r:
                r.raise_for_status()
                if r.status_code != 206 or r.headers.get('Content-Range', '').split('/')[0] != f'bytes {current}-{end}':
                    raise RuntimeError(f'Invalid range response: {r.status_code} {r.headers.get("Content-Range")}')
                begin = time.monotonic()
                with temp.open('ab') as out:
                    for block in r.iter_content(65536):
                        out.write(block)
                        if time.monotonic() - begin > 60:
                            raise TimeoutError('Reconnecting slow range with saved progress')
            if path.with_suffix('.tmp').stat().st_size != end - start + 1:
                raise RuntimeError('Truncated range')
            path.with_suffix('.tmp').replace(path)
            print(f'part {i} complete', flush=True)
            return path
        except Exception as e:
            print(f'part {i} attempt {attempt + 1}: {e}', flush=True)
            if attempt == 19:
                raise
            time.sleep(2 + attempt)

with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
    paths = list(pool.map(fetch, range((SIZE + CHUNK - 1) // CHUNK)))
destination = ROOT / 'models' / NAME
digest = hashlib.sha256()
with destination.with_suffix('.assembling').open('wb') as out:
    for path in paths:
        with path.open('rb') as source:
            while block := source.read(8 * 1024 * 1024):
                digest.update(block)
                out.write(block)
assert digest.hexdigest() == FILE['lfs']['sha256'], 'Model SHA256 mismatch'
destination.with_suffix('.assembling').replace(destination)
print(f'VERIFIED {destination} sha256={digest.hexdigest()}', flush=True)
