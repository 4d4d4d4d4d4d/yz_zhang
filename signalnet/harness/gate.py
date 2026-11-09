#!/usr/bin/env python3
"""SignalNet 质量门禁。入库前必须全部通过：`python3 harness/gate.py`

门禁列表（顺序执行，全部运行后汇总）：
  docs      必备文档存在；SPEC 需求表格式合法、ID 唯一、含 Last-Reviewed 日期
  layers    分层依赖：只能依赖同层或更低层；ranking/reputation 禁止依赖 ads；
            机制层（L0-L2）禁止 import random/time/socket 等非确定性/IO 模块
  lint      ruff check + ruff format --check
  tests     unittest 全量
  trace     每条 P0 需求至少被一个测试引用；测试引用的需求必须存在于 SPEC
  demo      端到端仿真冒烟：日志可校验、重放状态一致

用法：
  python3 harness/gate.py                # 全部门禁
  python3 harness/gate.py --only tests   # 单个门禁
  python3 harness/gate.py --json out.json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "signalnet"
TESTS = ROOT / "tests"
SPEC = ROOT / "docs" / "SPEC.md"

REQUIRED_DOCS = [
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "TODO.md",
    "docs/VISION.md",
    "docs/SPEC.md",
    "docs/ARCHITECTURE.md",
    "docs/ROADMAP.md",
]

LAYERS = {
    "crypto": 0,
    "ledger": 0,
    "content": 1,
    "attestation": 1,
    "fingerprint": 1,
    "reputation": 2,
    "ranking": 2,
    "ads": 2,
    "federation": 2,
    "node": 3,
    "cli": 3,
    "__main__": 3,
    "__init__": 3,
}
FORBIDDEN_EDGES = {("ranking", "ads"), ("reputation", "ads"), ("ranking", "node")}
NONDETERMINISTIC = {"random", "time", "datetime", "socket", "urllib", "requests", "secrets", "uuid"}
# crypto 允许生成随机密钥（Identity.generate），这是唯一例外，且不影响共识计算
NONDET_EXEMPT = {"crypto"}

REQ_ROW = re.compile(r"^\|\s*(REQ-[A-Z]{2}-\d{3})\s*\|\s*(P[0-2])\s*\|", re.M)
REQ_REF = re.compile(r"REQ-[A-Z]{2}-\d{3}")


@dataclass
class Result:
    name: str
    ok: bool
    details: list[str] = field(default_factory=list)


def parse_spec() -> dict[str, str]:
    """返回 {REQ-ID: 优先级}，保持 SPEC 中的顺序。"""
    text = SPEC.read_text(encoding="utf-8") if SPEC.exists() else ""
    out: dict[str, str] = {}
    for rid, pri in REQ_ROW.findall(text):
        out.setdefault(rid, pri)
    return out


def test_refs() -> set[str]:
    refs: set[str] = set()
    for p in TESTS.rglob("*.py"):
        refs |= set(REQ_REF.findall(p.read_text(encoding="utf-8")))
    return refs


# ---------------- 门禁实现 ----------------
def gate_docs() -> Result:
    errs = [f"缺少文档 {d}" for d in REQUIRED_DOCS if not (ROOT / d).exists()]
    if SPEC.exists():
        text = SPEC.read_text(encoding="utf-8")
        if not re.search(r"Last-Reviewed:\s*\d{4}-\d{2}-\d{2}", text):
            errs.append("SPEC 缺少 `Last-Reviewed: YYYY-MM-DD`")
        ids = [rid for rid, _ in REQ_ROW.findall(text)]
        dups = sorted({i for i in ids if ids.count(i) > 1})
        if dups:
            errs.append(f"SPEC 需求 ID 重复: {dups}")
        if not ids:
            errs.append("SPEC 未解析到任何需求行（格式：| REQ-XX-000 | P0 | ... |）")
    return Result("docs", not errs, errs)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.module:
                    mods.add("." + node.module.split(".")[0])
                else:
                    mods |= {"." + a.name for a in node.names}
            elif node.module:
                mods.add(node.module.split(".")[0])
    return mods


def gate_layers() -> Result:
    errs: list[str] = []
    for p in sorted(SRC.glob("*.py")):
        mod = p.stem
        if mod not in LAYERS:
            errs.append(f"{mod}: 未在 harness/gate.py LAYERS 中登记层级")
            continue
        for imp in _imports(p):
            if imp.startswith("."):
                dep = imp[1:]
                if dep not in LAYERS:
                    continue
                if LAYERS[dep] > LAYERS[mod]:
                    errs.append(f"{mod}(L{LAYERS[mod]}) -> {dep}(L{LAYERS[dep]}) 违反分层")
                if (mod, dep) in FORBIDDEN_EDGES:
                    errs.append(f"{mod} -> {dep} 是禁止的依赖（广告不得影响排序/声誉）")
            elif LAYERS[mod] <= 2 and mod not in NONDET_EXEMPT and imp in NONDETERMINISTIC:
                errs.append(f"{mod}: 机制层禁止 import {imp}（时间/随机数必须作为参数传入）")
    return Result("layers", not errs, errs)


def _run(cmd: list[str]) -> tuple[int, str]:
    env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT}"}
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    return p.returncode, (p.stdout + p.stderr).strip()


def gate_lint() -> Result:
    ruff = shutil.which("ruff")
    if not ruff:
        strict = os.environ.get("SIGNALNET_STRICT") == "1"
        return Result(
            "lint",
            not strict,
            [
                "未安装 ruff：pip install ruff"
                + ("（CI 严格模式失败）" if strict else "（本地跳过）")
            ],
        )
    errs: list[str] = []
    for cmd in ([ruff, "check", "."], [ruff, "format", "--check", "."]):
        code, out = _run(cmd)
        if code != 0:
            errs += out.splitlines()[-30:]
    return Result("lint", not errs, errs)


def gate_tests() -> Result:
    code, out = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."])
    lines = out.splitlines()
    summary = [line for line in lines if line.startswith(("Ran ", "OK", "FAILED"))]
    if code == 0:
        return Result("tests", True, summary)
    fails = [line for line in lines if line.startswith(("FAIL:", "ERROR:"))]
    return Result("tests", False, fails + summary + lines[-15:])


def gate_trace() -> Result:
    spec = parse_spec()
    refs = test_refs()
    errs = [
        f"{rid} [P0] 没有任何测试引用"
        for rid, pri in spec.items()
        if pri == "P0" and rid not in refs
    ]
    errs += [f"测试引用了 SPEC 中不存在的需求 {r}" for r in sorted(refs - set(spec))]
    covered = sum(1 for r in spec if r in refs)
    return Result("trace", not errs, errs or [f"已追溯 {covered}/{len(spec)} 条需求"])


def gate_demo() -> Result:
    code, out = _run([sys.executable, "-m", "signalnet", "demo"])
    if code != 0:
        return Result("demo", False, out.splitlines()[-10:])
    data = json.loads(out)
    errs = [k for k in ("ledger_ok", "replay_matches") if not data.get(k)]
    return Result("demo", not errs, [f"{k} 为 False" for k in errs])


GATES: dict[str, Callable[[], Result]] = {
    "docs": gate_docs,
    "layers": gate_layers,
    "lint": gate_lint,
    "tests": gate_tests,
    "trace": gate_trace,
    "demo": gate_demo,
}


def run_all(only: list[str] | None = None) -> list[Result]:
    out = []
    for name, fn in GATES.items():
        if only and name not in only:
            continue
        try:
            out.append(fn())
        except Exception as e:  # 门禁本身崩溃也视为失败
            out.append(Result(name, False, [f"门禁异常: {e!r}"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", choices=list(GATES))
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    results = run_all(args.only)
    for r in results:
        print(f"[{'PASS' if r.ok else 'FAIL'}] {r.name}")
        for d in r.details[:40]:
            print(f"    {d}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
        )
    ok = all(r.ok for r in results)
    print("\n门禁结果:", "全部通过 ✅" if ok else "存在失败 ❌")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
