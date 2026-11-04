"""PACK-090（377 号 spec，V405）场景包测试里「只有标签里的口语才接得住」的提问，必须真的只靠标签。

每轮场景发掘都给几条口语提问，说它们只能靠标签接住，用来钉住标签。V402 逐条变异时发现：
六条提问里另有两个字和正文或标题撞上，去掉标签照样答得上，标签删了测试也不红。
检索按二字切片算分（notebook.terms / score），这件事肉眼看不出来，只能靠逐个变异才发现。

这里静态算一遍：把那条知识的标签全部拿掉，用同样的检索算分，还够得上「相关」（MIN_RELATED）就红。
首跑在 122 条里查出存量 11 条（V380~V389），已逐条换成真正只在标签里的说法。
"""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

from app.modules.notebook.service import MIN_RELATED, score, terms
from app.modules.packs import service as psvc
from app.modules.skills.service import expand_query

TESTS = Path(__file__).parent
MARK = "只有标签里的口语才接得住"


def tag_only_questions() -> list[tuple[str, str, str, str]]:
    """（测试文件, 包 key, 提问, 应命中的知识标题）：取参数表里注释 MARK 之后的每一行。"""
    out = []
    for f in sorted(TESTS.glob("test_*.py")):
        src = f.read_text(encoding="utf-8")
        if MARK not in src or f.name == Path(__file__).name:
            continue
        marks = [i + 1 for i, line in enumerate(src.splitlines()) if MARK in line]
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.List) and node.elts and all(isinstance(e, ast.Tuple) for e in node.elts)):
                continue
            inside = [m for m in marks if node.lineno <= m <= node.end_lineno]
            if not inside:
                continue
            for e in node.elts:
                if e.lineno > inside[0]:
                    vals = [ast.literal_eval(x) for x in e.elts]
                    out.append((f.name, vals[0], vals[-2], vals[-1]))
    return out


def score_without_tags(key: str, q: str, title: str) -> int:
    d = json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))
    k = next(k for k in d["knowledge"] if k["title"] == title)
    return score(SimpleNamespace(title=k["title"], body=k["body"], tags=[], url=""), terms(expand_query(q, None)))


def test_the_scanner_sees_the_tag_only_questions():
    rows = tag_only_questions()
    assert len(rows) >= 100, f"只扫到 {len(rows)} 条：参数表的写法变了？"
    assert {r[0] for r in rows} >= {"test_v402_packs.py", "test_v391_packs.py"}


def test_tag_only_questions_really_need_the_tags():
    weak = [(f, q, title, s) for f, key, q, title in tag_only_questions()
            if (s := score_without_tags(key, q, title)) >= MIN_RELATED]
    assert not weak, ("这些提问去掉标签照样答得上，标签删了测试也不会红；换成只在标签里、和正文标题没有两字重叠的说法：\n"
                      + "\n".join(f"  {f}：「{q}」→「{t}」不靠标签也得 {s} 分" for f, q, t, s in weak))
