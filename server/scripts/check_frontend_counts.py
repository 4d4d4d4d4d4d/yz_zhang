"""DOC-011 文档里手抄的前端测试计数，与 vitest / jest 自己报的数比（103 号 spec）。

DOC-010（V111）只钉了后端计数，理由写在 `test_doc_counts.py` 里：前端计数的
权威来源是三套 npm 测试的输出，而后端回归里拿不到；用 AST 数 `it(` 是第二份
实现，`it.each` 一来就漂——**一个会误报的闸门会被人关掉**。

那条理由是对的，结论却不必是「不钉」：权威输出拿不到的是**后端回归**，
CI 的前端 job 自己就有。所以这里不数任何东西——vitest 与 jest 把真实结果
写成 JSON（两者同一组键），本脚本只做比对，在前端 job 里紧跟测试之后跑。

    python -m scripts.check_frontend_counts --dir <JSON 目录> core web
    python -m scripts.check_frontend_counts --dir <JSON 目录> app

只用标准库：前端 job 不装服务端依赖，这个脚本不能逼它装。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# 与 DOC-010 同一组文档：写着「现在是多少」的地方
DOCS = [REPO / "README.md", REPO / "docs" / "DELIVERY.md",
        REPO / "docs" / "OPERATIONS.md", REPO / "docs" / "SYSTEM-CHECK.md",
        REPO / "docs" / "GO-LIVE.md",
        REPO / "docs" / "specs" / "16-traceability.md",
        REPO / "docs" / "specs" / "72-status-ledger.md"]

# 文档里的叫法 -> 套件。「SDK」「共享 SDK」都是 packages/core。
SUITE_OF = {"web": "web", "sdk": "core", "core": "core", "app": "app"}
SUITES = ("core", "web", "app")

# 一处声明：「Web 138」「App **69** 项」「SDK 56 项」，后面同一句里要有「通过」或
# 「测试 / tests」——否则「SDK 266 个方法」这种**不是测试数**的也会被认成声明。
_CLAIM = re.compile(
    r"(?<![A-Za-z])(Web|web|SDK|core|App)\s*\*{0,2}(\d{2,4})\*{0,2}"
    r"(?=\s*(?:项|个)?\s*(?:[^。\n|]{0,40}?(?:通过|测试|tests)))")

# 「前端 N」是三套之和还是两套之和？V111 那次写的是「前端 161 tests（core 56 +
# web 84 + App 21）」，而 CI 里的前端 job 根本不跑 App。**一个没人说得清是哪几套
# 相加的数，没有办法核对**——所以现状声明里不许出现，只许按套件写。
_AMBIGUOUS_TOTAL = re.compile(r"前端\s*\*{0,2}(\d{2,4})\*{0,2}\s*(?:个|项)?\s*(?:测试|tests)")

# 不是「对现状的声明」的那些匹配 -> 为什么。值是理由，不是布尔（V90 那条）。
# 与 DOC-010 同一条规矩：历史记录不许为了闸门变绿被改掉。
HISTORICAL: dict[str, str] = {
    "链上 21 项、共享 SDK 56 项、Web 104 项通过":
        "DELIVERY 里 2026-10-07 商业化工程增量那一节的当时实况，带日期的小节就是历史记录",
    "链上测试 19 项、Web 102 项、共享 SDK 56 项、App 22 项":
        "DELIVERY 里 2026-10-07 智能合约增量（前次记录）的当时实况",
}


def _window(text: str, m: re.Match) -> str:
    return text[max(0, m.start() - 60):m.end() + 60]


def scan(docs: list[Path] | None = None) -> tuple[list[tuple[str, str, int]], list[tuple[str, int]]]:
    """-> ([(文档, 套件, 数字)], [(文档, 「前端 N」的 N)])，历史条目已剔除。"""
    claims: list[tuple[str, str, int]] = []
    ambiguous: list[tuple[str, int]] = []
    for path in docs or DOCS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(REPO))
        for m in _CLAIM.finditer(text):
            if any(p in _window(text, m) for p in HISTORICAL):
                continue
            claims.append((rel, SUITE_OF[m.group(1).lower()], int(m.group(2))))
        for m in _AMBIGUOUS_TOTAL.finditer(text):
            if any(p in _window(text, m) for p in HISTORICAL):
                continue
            ambiguous.append((rel, int(m.group(1))))
    return claims, ambiguous


def passed_count(result_file: Path) -> int:
    """vitest 的 json reporter 与 jest 的 --json 写的是同一组键。

    读 `numPassedTests` 而不是 `numTotalTests`：文档写的是「N 项通过」。
    有失败的结果不拿来比——那时该看的是失败，不是计数。
    """
    data = json.loads(result_file.read_text(encoding="utf-8"))
    for key in ("numPassedTests", "numFailedTests", "success"):
        if key not in data:
            raise ValueError(f"{result_file} 不像 vitest/jest 的 JSON 结果（缺 {key}）")
    if data["numFailedTests"] or not data["success"]:
        raise ValueError(f"{result_file}：有 {data['numFailedTests']} 项失败，先修测试")
    return int(data["numPassedTests"])


def check(result_dir: Path, suites: list[str], docs: list[Path] | None = None) -> list[str]:
    """-> 问题清单；空表示一致。"""
    problems: list[str] = []
    claims, ambiguous = scan(docs)
    for doc, n in ambiguous:
        problems.append(f"{doc}：「前端 {n}」说不清是哪几套相加，按套件写（Web / SDK / App）")
    for suite in suites:
        if suite not in SUITES:
            problems.append(f"未知套件 {suite}（只有 {', '.join(SUITES)}）")
            continue
        f = result_dir / f"{suite}.json"
        if not f.exists():
            # 拿不到结果就不许绿：「没比」不是「比过了一致」
            problems.append(f"没有 {f}——测试那一步没写 JSON，这一步就什么都没比")
            continue
        try:
            actual = passed_count(f)
        except ValueError as e:
            problems.append(str(e))
            continue
        for doc, s, n in claims:
            if s == suite and n != actual:
                problems.append(f"{doc}：写着 {suite} {n}，真实通过 {actual}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, type=Path, help="vitest/jest JSON 结果所在目录")
    ap.add_argument("suites", nargs="+", help="要比的套件：core / web / app")
    args = ap.parse_args(argv)
    problems = check(args.dir, args.suites)
    if problems:
        print("文档里的前端计数与真实结果不一致：", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print("改文档，不要改比对——数字的权威来源是测试框架自己的输出。", file=sys.stderr)
        return 1
    print(f"前端计数一致：{', '.join(args.suites)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
