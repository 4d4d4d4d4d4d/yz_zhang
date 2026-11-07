"""LINT-009 同一个模块里不许有两个同名的顶层函数 / 类。

V342 在 admin/router.py 里新写了一个 `_pending_request`（临时角色申请），恰好与 API 配额申请那边已有的同名函数撞了：
后定义的悄悄盖掉前一个，配额申请的批准 / 驳回全部 500。ruff 的 F811 只抓「重定义了一个**没用过**的名字」，
前一个早就被调用过，所以没红；全量回归跑到那几条测试才发现。这里直接按语法树查：同名就红。
"""
import ast
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _duplicates(src: str) -> list[str]:
    names = [n.name for n in ast.parse(src).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    return sorted(k for k, v in Counter(names).items() if v > 1)


def test_the_check_sees_a_redefinition():
    assert _duplicates("def a():\n    pass\n\na()\n\ndef a(x):\n    pass\n") == ["a"]
    assert _duplicates("def a():\n    pass\n\ndef b():\n    pass\n") == []


def test_no_module_defines_the_same_top_level_name_twice():
    bad = {}
    for p in sorted(APP.rglob("*.py")):
        dup = _duplicates(p.read_text(encoding="utf-8"))
        if dup:
            bad[str(p.relative_to(APP.parent))] = dup
    assert not bad, f"同一个模块里有同名的顶层函数 / 类，后一个会悄悄盖掉前一个：{bad}"
