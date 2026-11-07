"""PACK-094（432 号 spec）场景包测试的变异红验：从测试文件里自动推出要改坏的地方，逐个改坏、跑测试、改回。

    python -m scripts.pack_mutate tests/test_v458_packs.py          # 逐个改坏并跑，列出谁没变红
    python -m scripts.pack_mutate tests/test_v458_packs.py --list   # 只列出会改哪些地方，不跑

为什么要有它：第五十四轮起每批场景包 spec 都写「scratchpad/mutXXX.py 共 N 处，全红」，
可那些脚本放在会话的临时目录里，换一个容器就没了，后来的人没法复现那句「全红」。
这里不读手写配置，直接从测试文件推出三类变异，新的一批写完测试就能跑：

- 关键禁止项：测试里写了 `any("…" in f for f in a.forbidden)` 的，在那个包的种子文件里删掉含这段话的禁止项，
  跑那条测试函数；
- 只靠标签的问法：参数表里注释「只有标签里的口语才接得住」之后的每一行，删掉那条知识里被问法命中的标签，
  跑那一行（按参数下标选 `phonesN`）；
- 类目：测试里 `_categories()["…"]` 提到的类目，在 `task/service.py` 的种子类目里：不要资质的加一个
  `"required_cert": "x"`，已经要资质的去掉它（往前插同名键会被后写的覆盖，是等价变异），跑整个测试文件。

每处改坏之后都在 finally 里改回原文。有一处没变红就以非 0 退出。
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
SEEDS = SERVER / "app" / "modules" / "packs" / "seeds"
CATEGORY_SRC = SERVER / "app" / "modules" / "task" / "service.py"
MARK = "只有标签里的口语才接得住"
_FORBIDDEN_ASSERT = re.compile(r'any\("([^"]+)" in f for f in a\.forbidden\)')
_LOAD = re.compile(r'_load\("([a-z0-9-]+)"\)')
_CATEGORY = re.compile(r'_categories\(\)\["([^"]+)"\]')


@dataclass
class Mutation:
    kind: str          # forbidden / tag / category
    path: Path
    old: str
    new: str
    select: str        # 交给 pytest -k 的选择式；空串表示整个文件
    label: str


def _seed_text(key: str) -> str:
    return (SEEDS / f"{key}.json").read_text(encoding="utf-8")


def _remove_list_item(text: str, item: str) -> tuple[str, str]:
    """JSON 列表里删掉一项：返回（原文片段, 替换片段）。写法同种子文件：`"a", "b"` 一行一个列表。"""
    if text.count(f'"{item}"') != 1:
        raise LookupError(f"「{item}」在种子文件里出现 {text.count(chr(34) + item + chr(34))} 次，不是唯一的一项，没法自动改坏")
    for old in (f'"{item}", ', f', "{item}"', f'"{item}"'):
        if text.count(old) == 1:
            return old, ""
    raise LookupError(f"「{item}」在种子文件里不是唯一的一项，没法自动改坏")


def forbidden_mutations(src: str) -> list[Mutation]:
    out: list[Mutation] = []
    for node in ast.parse(src).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        body = ast.get_source_segment(src, node) or ""
        keys = _LOAD.findall(body)
        phrases = _FORBIDDEN_ASSERT.findall(body)
        if len(set(keys)) != 1 or not phrases:
            continue
        key = keys[0]
        import json

        forbidden: list[str] = []
        for a in json.loads(_seed_text(key))["assistants"]:
            forbidden.extend(a.get("forbidden", []))
        for phrase in phrases:
            hits = [f for f in forbidden if phrase in f]
            if len(hits) != 1:
                raise LookupError(f"{node.name}：「{phrase}」在 {key} 的禁止项里命中 {len(hits)} 条，要正好一条")
            old, new = _remove_list_item(_seed_text(key), hits[0])
            out.append(Mutation("forbidden", SEEDS / f"{key}.json", old, new, node.name, f"{key} 禁止项「{hits[0]}」"))
    return out


def tag_mutations(src: str) -> list[Mutation]:
    import json

    out: list[Mutation] = []
    marks = [i + 1 for i, line in enumerate(src.splitlines()) if MARK in line]
    for node in ast.walk(ast.parse(src)):
        if not (isinstance(node, ast.List) and node.elts and all(isinstance(e, ast.Tuple) for e in node.elts)):
            continue
        inside = [m for m in marks if node.lineno <= m <= node.end_lineno]
        if not inside:
            continue
        for idx, e in enumerate(node.elts):
            if e.lineno <= inside[0]:
                continue
            vals = [ast.literal_eval(x) for x in e.elts]
            key, q, title = vals[0], vals[-2], vals[-1]
            k = next(k for k in json.loads(_seed_text(key))["knowledge"] if k["title"] == title)
            hit = [t for t in k["tags"] if len(t) >= 2 and t in q]
            if len(hit) != 1:
                raise LookupError(f"「{q}」命中的标签是 {hit}，要正好一个（PACK-090 / V404）")
            old, new = _remove_list_item(_seed_text(key), hit[0])
            out.append(Mutation("tag", SEEDS / f"{key}.json", old, new, f"phones{idx}", f"{key} 标签「{hit[0]}」"))
    return out


def category_mutations(src: str) -> list[Mutation]:
    text = CATEGORY_SRC.read_text(encoding="utf-8")
    out: list[Mutation] = []
    for name in dict.fromkeys(_CATEGORY.findall(src)):
        found = re.findall(r'\{"name": "' + re.escape(name) + r'"[^}]*\}', text)
        if len(found) != 1:
            raise LookupError(f"类目「{name}」在 task/service.py 里出现 {len(found)} 次，要正好一次")
        old = found[0]
        req = re.search(r', "required_cert": [^,}]+', old)
        if req:      # 已经要资质的：去掉。往前插同名键没用——字典字面量里后写的覆盖先写的，是等价变异
            out.append(Mutation("category", CATEGORY_SRC, old, old.replace(req.group(0), ""), "", f"类目「{name}」去掉必选资质"))
        else:
            out.append(Mutation("category", CATEGORY_SRC, old, old[:-1] + ', "required_cert": "x"}', "", f"类目「{name}」加必选资质"))
    return out


def derive(test_file: Path) -> list[Mutation]:
    src = test_file.read_text(encoding="utf-8")
    return forbidden_mutations(src) + tag_mutations(src) + category_mutations(src)


def run_one(m: Mutation, test_file: Path) -> bool:
    """改坏一处、跑对应的测试、改回。返回 True 表示测试变红了（被杀死）。"""
    original = m.path.read_text(encoding="utf-8")
    if original.count(m.old) != 1:
        raise LookupError(f"{m.label}：原文在 {m.path.name} 里不是唯一的")
    m.path.write_text(original.replace(m.old, m.new), encoding="utf-8")
    try:
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test_file)]
        if m.select:
            cmd += ["-k", m.select]
        r = subprocess.run(cmd, cwd=SERVER, capture_output=True, text=True)
        return r.returncode == 1
    finally:
        m.path.write_text(original, encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    test_file = (SERVER / argv[0]).resolve() if not Path(argv[0]).is_absolute() else Path(argv[0])
    try:
        muts = derive(test_file)
    except LookupError as e:
        print(f"✗ {e}")
        return 2
    if "--list" in argv:
        for m in muts:
            print(f"{m.kind:9} {m.label}")
        print(f"共 {len(muts)} 处")
        return 0
    survived = 0
    for m in muts:
        red = run_one(m, test_file)
        survived += not red
        print(f"{'RED ' if red else 'SURV'} {m.label}", flush=True)
    print(f"{len(muts) - survived}/{len(muts)} 红")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
