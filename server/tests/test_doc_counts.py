"""DOC-010 文档里手抄的测试计数必须与真实数字一致（85 号 spec）。

由来：V109 那一批**刚刚做过完整的 doc sync**，把 README / DELIVERY /
追溯矩阵的计数从 1164 改成 1182，然后下一批一查——`OPERATIONS.md` 里
还有**两处** 1164。改了四份文档，漏了一份里的两处。

这不是粗心的问题，是机制的问题：同一个数字被手抄进五处，而**没有任何
东西在核对**。V57 早就立过同一条道理（「调度表是手抄的，手抄的清单一定
会漂移」），当时的结论是让调度器与声明表同源；这里同样——只不过文档不能
「同源」，那就让闸门去核对。

这一篇只钉**后端计数**，理由见 `_declared_backend_counts` 的注释。
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DOCS = [REPO / "README.md", REPO / "docs" / "DELIVERY.md",
        REPO / "docs" / "OPERATIONS.md", REPO / "docs" / "SYSTEM-CHECK.md",
        REPO / "docs" / "specs" / "16-traceability.md",
        REPO / "docs" / "specs" / "72-status-ledger.md"]

# 「N 个测试」，或者明确写着「后端 N tests」。
#
# 为什么不顺手把前端计数也扫进来：文档里写的是「前端 161 tests（core 56 +
# web 84 + App 21）」，而这几个数字的权威来源是三套 npm 测试的输出，
# 回归里拿不到（跑一遍要十几秒，且要 node 在位）。用 AST 数 `it(` 是第二份
# 实现，必然与 vitest/jest 的真实计数漂移（parametrize/each 就会差）——
# **一个会误报的闸门会被人关掉**。前端计数的漂移记在 72 号台账（DOC-011）。
_PATTERNS = (
    # 「个测试」与「个后端测试」都要认。V113 查出台账里写着「有 1004 个后端测试」
    # 而真实是 1195——**第一版正则要求「个」后面紧跟「测试」，中间多两个字就瞎了**。
    # 这正是这类闸门最容易出的错：它不会报错，它只是什么都不查。
    re.compile(r"(\d{3,5})\s*个(?:后端|前端|客户端)?测试"),
    re.compile(r"后端\s*\*{0,2}(\d{3,5})\*{0,2}\s*tests"),
)


# 不是「对现状的声明」的那些匹配 -> 为什么。值是理由，不是布尔（V90 那条）。
#
# 闸门要钉的是**过期的现状声明**，而历史记录不该为了让闸门变绿被改掉——
# 72 号台账第 3 节已经立过这条：「那些段落是当时的实况记录，改掉就失去了
# 『当时知道什么』的价值」。所以这里给它们一张明账，而不是把正则调窄到
# 谁也说不清它在查什么。
HISTORICAL: dict[str, str] = {
    "改了 314 个测试":
        "这是「改动了 314 个测试文件里的断言」，不是套件规模——量词一样，含义不同",
    "改坏之前 703 个测试全绿":
        "V45 当时的实况记录：那个缺陷在 703 个测试下全绿。改成今天的数字等于伪造当时的证据",
    # 下面两条是 V111 自己的探针输出，被**逐字引用**在追溯矩阵里当证据。
    # 这是这张表最需要处理的一类：**对「当时」的引用，不是对「现在」的声明**。
    # 注意豁免短语里带着 1164 这个具体数字——所以它挡不住将来任何别的过期值
    # （比如有人把某处写成 1250），豁免的范围正好等于这条引用本身。
    "已被 **1164 个测试**覆盖":
        "V111 探针输出的逐字引用（OPERATIONS 当时漏改的那一处），改掉它等于删掉证据",
    "有 1164 个测试钉着":
        "同上：探针里 OPERATIONS 第二处漏改的原文引用",
    "1004 个后端测试」":
        "V113/V114 在台账与追溯矩阵里**引用**的旧值（当时写着 1004，真实 1200），"
        "是对「当时」的引用而不是对「现在」的声明；删掉它就看不出这一节修了什么。"
        "键里带着 1004 这个具体数字，所以它挡不住将来任何别的过期值",
}


def _declared_backend_counts() -> dict[str, list[int]]:
    """文档 -> 它声明的后端测试数（可能多处）。"""
    out: dict[str, list[int]] = {}
    for path in DOCS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        found = []
        for pat in _PATTERNS:
            for m in pat.finditer(text):
                window = text[max(0, m.start() - 30):m.end() + 10]
                if any(phrase in window for phrase in HISTORICAL):
                    continue
                found.append(int(m.group(1)))
        if found:
            out[str(path.relative_to(REPO))] = found
    return out


def _actual_backend_count() -> int:
    """真实数字只有一个权威来源：pytest 自己数。

    不自己数 `def test_` ——parametrize 会让两边差一截，而一个算不准的
    闸门比没有闸门更糟（它会红在没问题的时候，然后被人关掉）。
    """
    # 这个子进程是在**父 pytest 正在跑**的时候起的，而收集会 import conftest。
    # conftest 用 `setdefault` 读库地址，所以这里显式给它一个一次性库——
    # 否则两个 pytest 共用 `test_platform.db`，而「同时跑两个 pytest」
    # 正是这个仓里已知会互相踩的事。**闸门自己不许成为别的测试的干扰源。**
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/collect.db"
        # conftest 在 import 时就会查 `faq_entries` 与 `decomposition_templates`
        # （它们喂 parametrize），所以空文件不行，得先有表。
        # 用 alembic 而不是 `create_all`：后者试过，漏了 `decomposition_templates`，
        # 而**迁移是这个仓里唯一保证能建出全部 88 张表的路径**（DEP-020）。
        # 多花两三秒，换掉一整类「差几张表」的排查。
        env = {**os.environ, "PLATFORM_DATABASE_URL": url}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(REPO / "server"), env=env, check=True, capture_output=True)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
            cwd=str(REPO / "server"), capture_output=True, text=True, timeout=600, env=env)
    m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout)
    assert m, f"收集不到测试数，输出尾部：\n{proc.stdout[-800:]}"
    return int(m.group(1))


def test_doc010_scanner_finds_the_declared_counts():
    """扫不到等于全绿，是最糟的一种绿。

    这一条尤其必要：这个闸门整个价值就在于「它真的在几份文档里找到了数字」。
    正则写歪一点（比如漏掉 `**1182 tests**` 的星号）就会静默地什么都不查。
    """
    declared = _declared_backend_counts()
    assert len(declared) >= 4, f"只在 {len(declared)} 份文档里扫到计数，正则可能写歪了：{declared}"
    for must in ("README.md", "docs/DELIVERY.md", "docs/OPERATIONS.md"):
        assert must in declared, f"{must} 里明明写着测试计数，扫描却说没有"


def test_doc010_every_declared_count_matches_reality():
    """每一处手抄的计数都要等于 pytest 真实收集到的数。"""
    actual = _actual_backend_count()
    declared = _declared_backend_counts()
    wrong = {doc: nums for doc, nums in declared.items()
             if any(n != actual for n in nums)}
    assert not wrong, (
        f"真实后端测试数是 {actual}，而这些文档写的不是：\n  "
        + "\n  ".join(f"{doc}: {nums}" for doc, nums in sorted(wrong.items()))
        + "\n改文档，不要改这条断言——数字的权威来源是 pytest 的输出。"
    )


def test_doc010_historical_table_stays_honest():
    """豁免表只许放「不是现状声明」的东西，且不许留已经不在文档里的条目。

    没有这一条，上面那张表就会变成「把红掉的数字塞进来就好了」的后门——
    那正是 82 号 spec 在豁免理由里禁掉「还没做」的同一个道理。
    """
    text = "\n".join(p.read_text(encoding="utf-8") for p in DOCS if p.exists())
    for phrase, why in sorted(HISTORICAL.items()):
        assert phrase in text, f"豁免表里的「{phrase}」已经不在文档里了，删掉它"
        assert len(why) >= 12, f"「{phrase}」的豁免理由太短：{why}"
        for excuse in ("还没做", "待补", "TODO", "以后", "懒得"):
            assert excuse not in why, f"「{phrase}」的理由是欠账不是理由：{why}"
