"""工程 harness：spec 脚手架、文档与待办检查、列待办（根目录 CLAUDE.md，skill spec-batch）。

    python -m scripts.harness new-spec "标题" --batch V147 --ids KB-100~110 [--slug personal-knowledge-base]
    python -m scripts.harness check        # spec 索引 / 状态行 / 待办 / skills / CLAUDE.md，有问题就非零退出
    python -m scripts.harness backlog      # 列出没做完的批次
    python -m scripts.harness closeout V152  # 一批的收尾清单：打钩、spec、台账、愿景、现状、没做的去处（skill iterate）

只用标准库：回归脚本与 CI 都能直接跑。
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPECS = REPO / "docs" / "specs"
INDEX = SPECS / "README.md"
BACKLOG = REPO / "docs" / "BACKLOG.md"
SKILLS = REPO / ".claude" / "skills"
CLAUDE = REPO / "CLAUDE.md"
LEDGER_NAME = "72-status-ledger.md"
VISION = REPO / "docs" / "VISION.md"
# 「没做的」里的编号：KB-110、SPACE-023b、APPB-050b……
OPEN_ID = re.compile(r"\b([A-Z][A-Z0-9]{1,6}(?:-[A-Z]+)?-\d{2,3}[a-z]?)\b")
STATUSES = ("todo", "doing", "done", "外")
# 从这一篇起 spec 必须有状态行（更早的 spec 写法不一，不追溯）
STATUS_REQUIRED_FROM = 113
# 从 harness 建立（121 号）起，做完的批次必须有「没做的」且编号有去处（更早的不追溯）
HARNESS_FROM = 121

TEMPLATE = """
# {num} {title}

> 状态：设计（{batch}）。编号 {ids}。
> 来源：（用户原话 / VISION 第几节 / BACKLOG 哪一行）
> 只增不减：（这一批不改动哪些既有行为）

## 0. 要解决的问题

## 1. 业界怎么做（带来源链接）

## 2. 数据

## 3. 接口

## 4. 两端

## 5. 隐私、授权与边界

## 6. 闸门与红验

| 闸门 | 红验 |
|---|---|

## 7. 没做的
"""


def spec_files() -> list[Path]:
    return sorted(p for p in SPECS.glob("[0-9]*.md"))


def spec_number(p: Path) -> int:
    return int(re.match(r"(\d+)", p.name).group(1))


def backlog_rows() -> list[dict]:
    rows = []
    for line in BACKLOG.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*(V\d+|—)\s*\|(.+?)\|\s*([\d—]+)\s*\|\s*(\S+)\s*\|(.*)\|\s*$", line)
        if m:
            rows.append({"batch": m.group(1), "title": m.group(2).strip(), "spec": m.group(3).strip(),
                         "status": m.group(4).strip(), "why": m.group(5).strip(), "line": line})
    return rows


def _status_line(p: Path) -> str:
    head = p.read_text(encoding="utf-8").splitlines()[:12]
    return next((ln for ln in head if ln.startswith("> 状态：")), "")


def _todo_section(text: str) -> str | None:
    """spec 的「没做的」一节（到下一个二级标题为止）；没有这一节返回 None。"""
    m = re.search(r"^##[^\n]*没做的[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else None


def _section(text: str, num: str) -> str:
    """spec 的第 num 节（「## num. …」到下一个二级标题为止）；没有就是空串。"""
    m = re.search(rf"^## {re.escape(num)}\.[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


def _closeout_problems(rows: list[dict]) -> list[str]:
    """ITER-001 迭代范式（skill iterate，用户 2026-10-14）：做完要打钩、spec 要更新、没做的要有去处。"""
    problems: list[str] = []
    by_batch = {r["batch"]: r for r in rows}
    ledger = (SPECS / LEDGER_NAME).read_text(encoding="utf-8") if (SPECS / LEDGER_NAME).exists() else ""
    backlog = BACKLOG.read_text(encoding="utf-8")
    for p in spec_files():
        if spec_number(p) < HARNESS_FROM:
            continue
        m = re.search(r"实现（(V\d+)）", _status_line(p))
        if m and m.group(1) in by_batch and by_batch[m.group(1)]["status"] != "done":
            problems.append(f"{p.name} 写着已实现（{m.group(1)}），BACKLOG 里这一批还没打钩（不是 done）")
    for r in rows:
        if r["status"] != "done" or r["spec"] == "—":
            continue
        spec = next((p for p in spec_files() if spec_number(p) == int(r["spec"])), None)
        if spec is None or spec_number(spec) < HARNESS_FROM:
            continue
        section = _todo_section(spec.read_text(encoding="utf-8"))
        if section is None or not section.strip():
            problems.append(f"{spec.name}（{r['batch']} done）缺「没做的」一节：做完一批要写清还欠什么")
            continue
        for oid in sorted(set(OPEN_ID.findall(section))):
            if oid not in ledger and oid not in backlog:
                problems.append(f"{spec.name}「没做的」里的 {oid} 没有去处：写进台账（{LEDGER_NAME}）或排进 BACKLOG")
    return problems


def closeout(batch: str) -> list[tuple[bool, str]]:
    """一批的收尾清单（skill iterate 第 2 步）。每一项：(做了没, 说明)。"""
    rows = backlog_rows()
    row = next((r for r in rows if r["batch"] == batch), None)
    items: list[tuple[bool, str]] = [(row is not None and row["status"] == "done", f"BACKLOG：{batch} 打钩（done）并写上 spec 号")]
    spec = None
    if row and row["spec"] != "—":
        spec = next((p for p in spec_files() if spec_number(p) == int(row["spec"])), None)
    items.append((bool(spec and re.search(r"实现|复核", _status_line(spec))), "spec 状态行改成「本批实现（…）」"))
    section = _todo_section(spec.read_text(encoding="utf-8")) if spec else None
    items.append((bool(section and section.strip()), "spec「没做的」写清还欠什么"))
    ledger = (SPECS / LEDGER_NAME).read_text(encoding="utf-8")
    ids = sorted(set(OPEN_ID.findall(section or "")))
    homeless = [i for i in ids if i not in ledger and i not in BACKLOG.read_text(encoding="utf-8")]
    items.append((not homeless, "「没做的」编号都进了台账或 BACKLOG" + (f"（缺：{'、'.join(homeless)}）" if homeless else "")))
    items.append((batch in ledger, f"台账（{LEDGER_NAME}）有这一批的「已做」行"))
    vision = VISION.read_text(encoding="utf-8") if VISION.exists() else ""
    both = bool(re.search(rf"\|[^\n]*{batch}[^\n]*两端已接|两端已接[^\n]*{batch}", vision))
    # 没有用户界面的批次（安全、运维一类）：spec 第 4 节写明「不涉及 / 无界面」时，
    # 对照行带上批次号即可，不必假装「两端已接」（141 号 spec 收尾时补的规则）
    no_ui = bool(spec and re.search(r"不涉及|无界面", _section(spec.read_text(encoding="utf-8"), "4")))
    tagged = bool(re.search(rf"^\| V-[^\n]*{batch}", vision, re.M))
    items.append((both or (no_ui and tagged),
                  "VISION 对照行写「两端已接」并带批次号（spec 第 4 节写明不涉及界面的，带批次号即可）"))
    status_docs = sorted((REPO / "docs").glob("STATUS-*.md"))
    items.append((any(batch in d.read_text(encoding="utf-8") for d in status_docs), "现状文档（docs/STATUS-*.md）划掉这一项"))
    nxt = next((r for r in rows if r["status"] in ("todo", "doing")), None)
    items.append((nxt is not None, f"下一批：{nxt['batch']} {nxt['title']}" if nxt else "BACKLOG 没有待办了：走 skill scenario-discovery 补"))
    return items


def check() -> list[str]:
    problems: list[str] = []
    index = INDEX.read_text(encoding="utf-8")
    for p in spec_files():
        if f"]({p.name})" not in index and f"](./{p.name})" not in index:
            problems.append(f"spec 没登记进索引 docs/specs/README.md：{p.name}")
        if spec_number(p) >= STATUS_REQUIRED_FROM and not _status_line(p):
            problems.append(f"spec 开头缺「> 状态：」行：{p.name}")
    nums = {}
    for p in spec_files():
        nums.setdefault(spec_number(p), []).append(p.name)
    for n, names in nums.items():
        if len(names) > 1 and n >= STATUS_REQUIRED_FROM:
            problems.append(f"spec 编号重复：{names}")
    rows = backlog_rows()
    if len(rows) < 5:
        problems.append("BACKLOG 读不出表格行（格式变了？）")
    for r in rows:
        if r["status"] not in STATUSES:
            problems.append(f"BACKLOG 状态只能是 {STATUSES}：{r['line']}")
        if r["spec"] != "—":
            matches = [p for p in spec_files() if spec_number(p) == int(r["spec"])]
            if not matches:
                problems.append(f"BACKLOG 引用的 spec 不存在：{r['spec']}（{r['batch']}）")
            elif r["status"] == "done" and not re.search(r"实现|复核", _status_line(matches[0])):
                problems.append(f"BACKLOG 写着 done，而 {matches[0].name} 的状态行不是「实现 / 复核」")
        if r["status"] in ("todo", "doing") and r["batch"] == "—":
            problems.append(f"没排批次的待办只能是「外」：{r['line']}")
    for d in sorted(SKILLS.glob("*")) if SKILLS.exists() else []:
        f = d / "SKILL.md"
        text = f.read_text(encoding="utf-8") if f.exists() else ""
        if not re.match(r"^---\nname: [a-z0-9-]+\ndescription: .{40,}\n---\n", text):
            problems.append(f"skill 缺 frontmatter（name / description）：{d.name}")
    problems += _closeout_problems(rows)
    if not CLAUDE.exists() or "BACKLOG" not in CLAUDE.read_text(encoding="utf-8"):
        problems.append("根目录 CLAUDE.md 缺失或没有指向 docs/BACKLOG.md")
    return problems


def new_spec(title: str, batch: str, ids: str, slug: str = "") -> Path:
    num = max(spec_number(p) for p in spec_files()) + 1
    slug = slug or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or f"spec-{num}"
    path = SPECS / f"{num}-{slug}.md"
    path.write_text(TEMPLATE.format(num=num, title=title, batch=batch, ids=ids or "（待定）"), encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    row = f"| {num} | {title} | [{path.name}](./{path.name}) | P0 |"
    m = re.search(r"^\| (\d+) \|.*\]\(\./\d+-.*\.md\) \|.*$", index, re.M)
    # 索引的近期部分按编号倒序：插在当前最大编号那一行前面
    rows = [(int(x.group(1)), x.start()) for x in re.finditer(r"^\| (\d+) \|", index, re.M)]
    top = max(rows, default=None, key=lambda t: t[0])
    if top and m:
        index = index[:top[1]] + row + "\n" + index[top[1]:]
    else:
        index = index.rstrip() + "\n" + row + "\n"
    INDEX.write_text(index, encoding="utf-8")
    shown = path.relative_to(REPO) if path.is_relative_to(REPO) else path
    print(f"已建 {shown}（{date.today().isoformat()}），并登记进索引")
    return path


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("new-spec", "check", "backlog", "closeout"):
        print(__doc__)
        return 2
    if argv[0] == "check":
        problems = check()
        print("\n".join(problems) if problems else "harness 检查通过")
        return 1 if problems else 0
    if argv[0] == "backlog":
        for r in backlog_rows():
            if r["status"] in ("todo", "doing"):
                print(f"{r['batch']}  [{r['status']}]  {r['title']}")
        return 0
    if argv[0] == "closeout":
        if len(argv) < 2:
            print("用法：closeout V1xx")
            return 2
        items = closeout(argv[1])
        for ok, text in items:
            print(("[x] " if ok else "[ ] ") + text)
        return 0 if all(ok for ok, _ in items) else 1
    args = argv[1:]
    title = args[0] if args and not args[0].startswith("--") else ""
    opts = {k: v for k, v in zip(args[1::2], args[2::2])} if title else {}
    if not title:
        print("用法：new-spec \"标题\" --batch V1xx --ids XXX-001~010 [--slug english-slug]")
        return 2
    new_spec(title, opts.get("--batch", "V?"), opts.get("--ids", ""), opts.get("--slug", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
