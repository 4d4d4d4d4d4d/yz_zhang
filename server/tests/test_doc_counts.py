"""DOC-010 文档里手抄的测试计数必须与真实数字一致（85 号 spec）。

由来：V109 那一批**刚刚做过完整的 doc sync**，把 README / DELIVERY /
追溯矩阵的计数从 1164 改成 1182，然后下一批一查——`OPERATIONS.md` 里
还有**两处** 1164。改了四份文档，漏了一份里的两处。

这不是粗心的问题，是机制的问题：同一个数字被手抄进五处，而**没有任何
东西在核对**。V57 早就立过同一条道理（「调度表是手抄的，手抄的清单一定
会漂移」），当时的结论是让调度器与声明表同源；这里同样——只不过文档不能
「同源」，那就让闸门去核对。

V111 只钉了后端计数。V129（103 号 spec）补上另外两类：

- **前端计数（DOC-011）**：权威来源是 vitest / jest 自己的输出，回归里拿不到——
  所以比对放在 CI 的前端 job 里紧跟测试之后跑（`scripts/check_frontend_counts.py`），
  这里钉的是**那一步真的在那儿**、比对逻辑真的会红、扫描器真的扫得到。
- **结构计数（DOC-012）**：表数、迁移条数、job 数——这三样回归里算得出来，直接比。
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
    # V129 查出的第三种写法：「后端 850 测试」——没有「个」、也不是 tests。
    # OPERATIONS 里描述 CI 的那一句就这么写，从 V111 起一直是 850，闸门看不见。
    # 与 V113 那次（「个**后端**测试」）同一类：**它不会报错，它只是什么都不查**。
    re.compile(r"后端\s*\*{0,2}(\d{3,5})\*{0,2}\s*测试"),
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
        # 而**迁移是这个仓里唯一保证能建出全部表的路径**（DEP-020）。
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
    # 三种写法各自要认得——每一种都曾经让这个闸门瞎过
    for sample in ("有 1234 个测试", "有 1234 个后端测试", "后端 **1234 tests**", "后端 1234 测试"):
        assert any(p.search(sample) for p in _PATTERNS), f"认不出「{sample}」"


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


# ====================================================================== DOC-011
# 前端计数：比对在 CI 里，这里钉「比对真的在那儿、真的会红、真的扫得到」。
from scripts import check_frontend_counts as fe  # noqa: E402

CI = REPO / ".github" / "workflows" / "ci.yml"


def _result(tmp: Path, suite: str, passed: int, failed: int = 0) -> None:
    """vitest json reporter 与 jest --json 的同一组键（V129 实测两者一致）。"""
    import json

    (tmp / f"{suite}.json").write_text(json.dumps({
        "numTotalTests": passed + failed, "numPassedTests": passed,
        "numFailedTests": failed, "numPendingTests": 0, "success": failed == 0,
    }), encoding="utf-8")


def test_doc011_scanner_finds_each_suites_claim():
    """扫不到等于全绿。DELIVERY 顶上那一行写着三套的数，三套都要认出来。"""
    claims, _ = fe.scan()
    suites = {s for doc, s, _n in claims if doc == "docs/DELIVERY.md"}
    assert suites == {"core", "web", "app"}, f"DELIVERY 里只认出了 {suites}"
    # 「SDK 266 个方法」不是测试数，不许被认成声明
    assert not fe._CLAIM.search("共享 SDK 266 个方法，web 调 188"), "把方法数认成了测试数"


def test_doc011_no_ambiguous_frontend_totals():
    """「前端 N 测试」说不清是哪几套相加——现状声明里不许出现。

    V129 查出 OPERATIONS 描述 CI 的那句写着「前端 64 测试」：真实是 SDK 56 +
    Web 138（+ App 69，而 CI 的前端 job 根本不跑 App）。它从 V5x 起就没动过。
    """
    _, ambiguous = fe.scan()
    assert not ambiguous, f"这些地方写着说不清的前端总数：{ambiguous}"


def test_doc011_comparison_goes_red_on_a_wrong_count(tmp_path):
    claims, _ = fe.scan()
    declared = {s: n for _d, s, n in claims}
    _result(tmp_path, "web", declared["web"] + 1)
    problems = fe.check(tmp_path, ["web"])
    assert any(p.startswith("docs/DELIVERY.md：写着 web") for p in problems), problems
    assert fe.main(["--dir", str(tmp_path), "web"]) == 1


def test_doc011_comparison_is_green_on_the_right_count(tmp_path):
    claims, _ = fe.scan()
    for suite in fe.SUITES:
        _result(tmp_path, suite, next(n for _d, s, n in claims if s == suite))
    assert fe.check(tmp_path, list(fe.SUITES)) == []
    assert fe.main(["--dir", str(tmp_path), *fe.SUITES]) == 0


def test_doc011_missing_or_failing_results_are_not_green(tmp_path):
    """「没比」不是「比过了一致」：拿不到结果、或结果里有失败，都不许绿。"""
    assert fe.check(tmp_path, ["app"]), "没有结果文件却判了一致"
    _result(tmp_path, "app", 69, failed=1)
    assert any("失败" in p for p in fe.check(tmp_path, ["app"]))
    (tmp_path / "core.json").write_text("{}", encoding="utf-8")
    assert any("不像" in p for p in fe.check(tmp_path, ["core"]))


def _ci_steps() -> dict[str, str]:
    """job 名 -> 那个 job 的原文。"""
    text = CI.read_text(encoding="utf-8")
    jobs = {}
    for m in re.finditer(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", text, re.M | re.S):
        jobs[m.group(1)] = m.group(2)
    return jobs


def test_doc011_ci_writes_results_and_compares_them_after_every_suite():
    """每一套都要：测试那一步写 JSON → 紧接着一步拿它比。不许 `|| true`。"""
    jobs = _ci_steps()
    assert {"frontend", "app-typecheck"} <= set(jobs), f"CI 的 job 认不出来：{sorted(jobs)}"
    expect = {"frontend": ("core", "web"), "app-typecheck": ("app",)}
    for job, suites in expect.items():
        body = jobs[job]
        cmp_at = body.find("scripts.check_frontend_counts")
        assert cmp_at >= 0, f"{job} 里没有比对那一步"
        cmp_line = body[cmp_at:body.find("\n", cmp_at)]
        for suite in suites:
            out = f"counts/{suite}.json"
            assert out in body, f"{job} 的测试没有把 {suite} 的结果写到 {out}"
            assert body.find(out) < cmp_at, f"{job}：{suite} 的比对排在了测试之前"
            assert re.search(rf"\b{suite}\b", cmp_line), f"{job} 的比对漏了 {suite}：{cmp_line}"
        for bad in ("|| true", "continue-on-error"):
            assert bad not in body, f"{job} 里有 {bad}——比对红了也不拦，等于没比"


def test_doc011_every_workspace_with_tests_is_run_in_ci():
    """CI 按工作区分开跑（两个工作区写同一个文件会互相覆盖）——那么新加一个
    带测试的工作区而忘了加进 CI，它的测试就**一条都不跑**。根上的 `npm test`
    此前会自动带上它，所以这一条是这次改动自己引入的风险，要自己钉住。"""
    import json

    root = json.loads((REPO / "package.json").read_text(encoding="utf-8"))
    workspaces = []
    for pattern in root["workspaces"]:
        workspaces += [p for p in REPO.glob(pattern) if (p / "package.json").exists()]
    assert len(workspaces) >= 2, f"只扫到 {workspaces}"
    front = _ci_steps()["frontend"]
    for ws in workspaces:
        pkg = json.loads((ws / "package.json").read_text(encoding="utf-8"))
        if "test" not in pkg.get("scripts", {}):
            continue
        rel = ws.relative_to(REPO).as_posix()
        assert f"npm test -w {rel} " in front, f"工作区 {rel} 有测试，而 CI 的前端 job 不跑它"


def test_doc011_historical_table_stays_honest():
    """与 DOC-010 同一条：只放「不是现状声明」的东西；每一条都必须真的挡掉了
    一处匹配——一条什么都没挡的豁免只是噪音，而且它会让人以为那里有东西。"""
    texts = {p: p.read_text(encoding="utf-8") for p in fe.DOCS if p.exists()}
    for phrase, why in sorted(fe.HISTORICAL.items()):
        hit = [t for t in texts.values() if phrase in t]
        assert hit, f"豁免表里的「{phrase}」已经不在文档里了，删掉它"
        suppresses = any(
            phrase in fe._window(t, m)
            for t in hit for pat in (fe._CLAIM, fe._AMBIGUOUS_TOTAL) for m in pat.finditer(t))
        assert suppresses, f"「{phrase}」没有挡掉任何一处匹配，删掉它"
        assert len(why) >= 12, f"「{phrase}」的豁免理由太短：{why}"
        for excuse in ("还没做", "待补", "TODO", "以后", "懒得"):
            assert excuse not in why, f"「{phrase}」的理由是欠账不是理由：{why}"


# ====================================================================== DOC-012
# 结构计数：表、迁移、job。这三样回归里算得出来，直接比。
_STRUCT = {
    "tables": re.compile(r"(\d{1,4})\s*张表"),
    "migrations": re.compile(r"(\d{1,4})\s*条迁移"),
    "jobs": re.compile(r"(\d{1,3})\s*个\s*(?:定时任务|job)"),
}
STRUCT_DOCS = [*DOCS, REPO / "docs" / "GO-LIVE.md"]

# 整篇是某一天的快照 -> 证明它是快照的那句话。只有那句话还在，豁免才成立：
# 有人把它改成「当前状态」页而删了日期，它就重新受检。
SNAPSHOT_DOCS: dict[str, str] = {
    "docs/SYSTEM-CHECK.md": "体检日期：",
}

STRUCT_HISTORICAL: dict[str, str] = {
    "从零建库实测：32 条迁移":
        "DELIVERY 的 V109 那一行：当时的实测输出，同一句里的表数也是当时的",
    "22 个定时任务**逐个 POST 真跑":
        "DELIVERY 的 V109 那一行，记的是那一次真跑了多少个",
    "V109 实测，32 条迁移":
        "OPERATIONS 引用 V109 那一次从零建库的实测，括号里写明了是哪一次",
    "个 job 有记录":
        "冒烟脚本的一行输出原文（「0 个 job 有记录」），是那行输出本身，不是 job 的数量",
    "DEP-051 22 个 job 逐个真跑":
        "追溯矩阵里 V109 那一批的行，记的是那一次真跑了多少个",
    "OPS-011 cron 端点鉴权":
        "追溯矩阵里 OPS-011 那一批的行：当时修的是 7 个 job 的鉴权，不是 job 总数",
}


def _structural_claims(raw: bool = False) -> list[tuple[str, str, int]]:
    out = []
    for path in STRUCT_DOCS:
        if not path.exists():
            continue
        rel = str(path.relative_to(REPO))
        text = path.read_text(encoding="utf-8")
        snapshot = SNAPSHOT_DOCS.get(rel)
        for kind, pat in _STRUCT.items():
            for m in pat.finditer(text):
                if not raw:
                    if snapshot and snapshot in text:
                        continue
                    window = text[max(0, m.start() - 60):m.end() + 60]
                    if any(p in window for p in STRUCT_HISTORICAL):
                        continue
                out.append((rel, kind, int(m.group(1))))
    return out


def _actual_structure() -> dict[str, int]:
    """表数从迁移真的建一遍数（不是数模型）；迁移数问 alembic；job 数读调度表。"""
    import sqlalchemy as sa
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.jobs import JOBS

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/structure.db"
        env = {**os.environ, "PLATFORM_DATABASE_URL": url}
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       cwd=str(REPO / "server"), env=env, check=True, capture_output=True)
        engine = sa.create_engine(url)
        try:
            tables = [t for t in sa.inspect(engine).get_table_names() if t != "alembic_version"]
        finally:
            engine.dispose()
    script = ScriptDirectory.from_config(Config(str(REPO / "server" / "alembic.ini")))
    return {"tables": len(tables),
            "migrations": len(list(script.walk_revisions())),
            "jobs": len(JOBS)}


def test_doc012_scanner_sees_all_three_kinds():
    """扫不到等于全绿：三类写法在文档里都出现过（哪怕是历史），扫描器都要认出来。"""
    kinds = {k for _d, k, _n in _structural_claims(raw=True)}
    assert kinds == set(_STRUCT), f"只认出了 {kinds}"
    current = _structural_claims()
    assert any(d == "docs/GO-LIVE.md" and k == "jobs" for d, k, _n in current), (
        "GO-LIVE 的上线手册里写着 /jobz 应该看到几个 job，扫描却说没有")


def test_doc012_structural_counts_match_reality():
    """V129 第一次跑：GO-LIVE 的上线手册写着「/jobz 18 个 job 在册」（真实 22），
    OPERATIONS 写着「全部 14 个 job 端点已接入」。前者是上线当天值班的人
    拿来对照的数——对不上时他只能猜是文档旧了还是 job 丢了。"""
    actual = _actual_structure()
    wrong = [(d, k, n) for d, k, n in _structural_claims() if n != actual[k]]
    assert not wrong, (
        f"真实：{actual}；这些地方写的不是：\n  "
        + "\n  ".join(f"{d}：{k} {n}" for d, k, n in wrong)
        + "\n改文档，不要改这条断言。"
    )


def test_doc012_exemptions_stay_honest():
    texts = {str(p.relative_to(REPO)): p.read_text(encoding="utf-8")
             for p in STRUCT_DOCS if p.exists()}
    for doc, marker in SNAPSHOT_DOCS.items():
        assert marker in texts.get(doc, ""), f"{doc} 已经不是快照了（找不到「{marker}」），删掉这条豁免"
    for phrase, why in sorted(STRUCT_HISTORICAL.items()):
        assert any(phrase in t for t in texts.values()), f"「{phrase}」已经不在文档里了，删掉它"
        assert len(why) >= 12, f"「{phrase}」的豁免理由太短：{why}"
        for excuse in ("还没做", "待补", "TODO", "以后", "懒得"):
            assert excuse not in why, f"「{phrase}」的理由是欠账不是理由：{why}"
