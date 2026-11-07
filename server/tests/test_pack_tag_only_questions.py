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

from app.modules.notebook.service import MIN_RELATED
from app.modules.packs import service as psvc

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
    # PACK-092（416 号 spec）与助手问答同一套打分（含「情态词前面的主题在标题里」那一条），不然闸门比真实检索宽
    return psvc.knowledge_score(k["title"], k["body"], [], psvc.pack_terms(q), q)


def test_the_scanner_sees_the_tag_only_questions():
    rows = tag_only_questions()
    assert len(rows) >= 100, f"只扫到 {len(rows)} 条：参数表的写法变了？"
    assert {r[0] for r in rows} >= {"test_v402_packs.py", "test_v391_packs.py"}


def test_each_tag_only_question_leans_on_exactly_one_tag():
    """V404（378 号 spec）：一句里含两个标签（「前任要来查记录」含「前任」「查记录」），删掉其中一个另一个照样接住，
    逐个标签变异就测不出来。每条「只靠标签」的提问只许命中那条知识的一个标签。"""
    many = []
    for f, key, q, title in tag_only_questions():
        d = json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))
        k = next(k for k in d["knowledge"] if k["title"] == title)
        hit = [t for t in k["tags"] if len(t) >= 2 and t in q]
        if len(hit) != 1:
            many.append((f, q, hit))
    assert not many, ("这些提问命中的标签不是正好一个（删一个标签还有别的接住，或者一个都没命中）：\n"
                      + "\n".join(f"  {f}：「{q}」命中 {hit}" for f, q, hit in many))


def test_tag_only_questions_really_need_the_tags():
    weak = [(f, q, title, s) for f, key, q, title in tag_only_questions()
            if (s := score_without_tags(key, q, title)) >= MIN_RELATED]
    assert not weak, ("这些提问去掉标签照样答得上，标签删了测试也不会红；换成只在标签里、和正文标题没有两字重叠的说法：\n"
                      + "\n".join(f"  {f}：「{q}」→「{t}」不靠标签也得 {s} 分" for f, q, t, s in weak))


def pinned_score(k: dict, q: str) -> int:
    """PACK-093（422 号 spec）只拿掉问法命中的那个标签、其余标签留着，这条知识还得几分。
    （问法里直接出现的标签已经全拿掉了，「标签整个在问题里」的加分在这里恒为 0，不再算。）"""
    rest = [t for t in k["tags"] if not (len(t) >= 2 and t in q)]
    return psvc.knowledge_score(k["title"], k["body"], rest, psvc.pack_terms(q), q)


def score_without_pinned_tag(key: str, q: str, title: str) -> int:
    d = json.loads((psvc.SEEDS / f"{key}.json").read_text(encoding="utf-8"))
    return pinned_score(next(k for k in d["knowledge"] if k["title"] == title), q)


def test_tag_only_questions_need_that_one_tag():
    """PACK-093（422 号 spec，V449）：上面那条把标签**全拿掉**再算；逐个标签变异却只删一个。
    421 号「话筒没电」删掉后，同一条知识的另一个标签「没电了」的切片补上了，测试不红。
    这里只拿掉命中的那一个，其余标签留着，还够得上「相关」就红。首跑 282 条里查出存量 1 条（「跑腿费怎么收」），已换标签。"""
    weak = [(f, q, title, s) for f, key, q, title in tag_only_questions()
            if (s := score_without_pinned_tag(key, q, title)) >= MIN_RELATED]
    assert not weak, ("这些提问只拿掉命中的标签、靠别的标签照样答得上，删这个标签测试也不会红；"
                      "换掉和它重叠的那个标签，或换一个问法：\n"
                      + "\n".join(f"  {f}：「{q}」→「{t}」靠别的标签也得 {s} 分" for f, q, t, s in weak))


def test_the_one_tag_check_sees_an_overlapping_tag():
    """扫描器自己的红验：给一条知识加一个和问法有切片重叠的标签，必须被查出来。"""
    from app.modules.notebook.service import MIN_RELATED as M

    k = {"title": "设备清单、型号、数量和备用写清", "body": "报价单列清音箱、调音台、话筒、灯具的型号和数量，备用话筒和电池写进去。"}
    assert pinned_score({**k, "tags": ["断音", "话筒没电"]}, "话筒没电") < M
    assert pinned_score({**k, "tags": ["没电了", "话筒没电"]}, "话筒没电") >= M
