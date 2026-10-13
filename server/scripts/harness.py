"""工程 harness：spec 脚手架、文档与待办检查、列待办（根目录 CLAUDE.md，skill spec-batch）。

    python -m scripts.harness new-spec "标题" --batch V147 --ids KB-100~110 [--slug personal-knowledge-base]
    python -m scripts.harness check        # spec 索引 / 状态行 / 待办 / skills / CLAUDE.md，有问题就非零退出
    python -m scripts.harness backlog      # 列出没做完的批次

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
STATUSES = ("todo", "doing", "done", "外")
# 从这一篇起 spec 必须有状态行（更早的 spec 写法不一，不追溯）
STATUS_REQUIRED_FROM = 113

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
    if not argv or argv[0] not in ("new-spec", "check", "backlog"):
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
