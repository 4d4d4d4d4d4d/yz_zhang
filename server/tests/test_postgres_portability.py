"""SQL 里不许拿列和 `[]` / `{}` 字面量比较（106 号 spec）。

V132 在本地 Postgres 上跑拆解测试撞见：`KnowledgeCard.decomposition != []` 在 SQLite 上
能跑，在 Postgres 上**没有 `json <> json` 这个运算符**——没有种子模板、也没命中关键词的
类目，生产上一发起分解就 500。测试库是 SQLite，这类错只有换了引擎才看得见；
所以把这个形状本身禁掉。要判断 JSON 是否为空，查出来在 Python 里判断。
"""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
QUERY_METHODS = {"filter", "where", "having"}


def _offenders(source: str, name: str = "<src>") -> list[str]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in QUERY_METHODS):
            continue
        for arg in node.args:
            for sub in ast.walk(arg):
                if isinstance(sub, ast.Compare) and any(
                        isinstance(c, (ast.List, ast.Dict)) for c in sub.comparators):
                    out.append(f"{name}:{sub.lineno} {ast.unparse(sub)}")
    return out


def test_scanner_sees_the_shape():
    """扫不到等于全绿：把 V132 修掉的那一行原样喂给它。"""
    bad = "db.query(K).filter(K.category == c, K.decomposition != []).first()"
    assert _offenders(bad), "扫描器认不出 V132 修掉的那个写法"
    assert _offenders("q.where(T.tags == {})")
    assert not _offenders("db.query(K).filter(K.category == c).first()")


def test_no_json_literal_comparisons_in_sql():
    found = []
    for f in APP.rglob("*.py"):
        found += _offenders(f.read_text(encoding="utf-8"), str(f.relative_to(APP)))
    assert not found, ("这些查询拿列和 [] / {} 比较，Postgres 上没有这个运算符：\n  "
                       + "\n  ".join(found))
