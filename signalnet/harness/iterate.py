#!/usr/bin/env python3
"""持续迭代“传感器”：运行门禁 → 发现问题 → 刷新 TODO.md 自动区 → 给出下一项任务。

它不自己写代码；它负责把“现在最该做什么”客观地算出来，交给人或 AI 代理执行
（执行协议见 AGENTS.md §4）。优先级：
  1. 🔴 门禁失败（阻断，必须先修）
  2. 🟠 SPEC 过期（Last-Reviewed 超过 SPEC_STALE_DAYS 天）
  3. 🟡 代码中的 TODO/FIXME
  4. 🔵 尚未实现/追溯的 P1 需求（先按 ROADMAP 编号顺序，其余按 SPEC 顺序）
  5. ⚪ P2 需求（远期）

用法：
  python3 harness/iterate.py            # 刷新 TODO.md 并打印下一项
  python3 harness/iterate.py --check    # 只打印，不写文件
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate

ROOT = gate.ROOT
TODO = ROOT / "TODO.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
REPORT = ROOT / "harness" / "reports" / "latest.json"
BEGIN, END = "<!-- AUTO:BEGIN -->", "<!-- AUTO:END -->"
SPEC_STALE_DAYS = 14
CODE_TODO = re.compile(r"#\s*(TODO|FIXME)[:：]?\s*(.*)")


def spec_titles() -> dict[str, str]:
    text = gate.SPEC.read_text(encoding="utf-8")
    out = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*(REQ-[A-Z]{2}-\d{3})\s*\|\s*P[0-2]\s*\|\s*([^|]+)\|", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def roadmap_order() -> list[str]:
    """ROADMAP 中编号列表 `1. **REQ-XX-000**` 给出的执行顺序。"""
    if not ROADMAP.exists():
        return []
    return re.findall(r"^\s*\d+\.\s*\*\*(REQ-[A-Z]{2}-\d{3})\*\*", ROADMAP.read_text("utf-8"), re.M)


def spec_age_days(today: dt.date) -> int | None:
    m = re.search(r"Last-Reviewed:\s*(\d{4}-\d{2}-\d{2})", gate.SPEC.read_text(encoding="utf-8"))
    if not m:
        return None
    return (today - dt.date.fromisoformat(m.group(1))).days


def collect(today: dt.date) -> tuple[list[gate.Result], list[tuple[str, str]]]:
    results = gate.run_all()
    items: list[tuple[str, str]] = []
    for r in results:
        if not r.ok:
            detail = "; ".join(r.details[:3])
            items.append(("🔴", f"门禁 `{r.name}` 失败：{detail}"))
    age = spec_age_days(today)
    if age is None or age > SPEC_STALE_DAYS:
        items.append(("🟠", f"SPEC 已 {age} 天未评审：按 AGENTS.md §5 复核并更新 Last-Reviewed"))
    for p in sorted(gate.SRC.rglob("*.py")):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            m = CODE_TODO.search(line)
            if m:
                items.append(("🟡", f"`{p.relative_to(ROOT)}:{n}` {m.group(1)} {m.group(2)}"))
    spec = gate.parse_spec()
    refs = gate.test_refs()
    titles = spec_titles()
    order = {rid: i for i, rid in enumerate(roadmap_order())}
    ranked = sorted(spec, key=lambda r: order.get(r, len(order)))  # 稳定排序：其余保持 SPEC 顺序
    for pri, icon in (("P1", "🔵"), ("P2", "⚪")):
        for rid in ranked:
            p = spec[rid]
            if p == pri and rid not in refs:
                items.append((icon, f"{rid} [{pri}] {titles.get(rid, '')}"))
    return results, items


def render(items: list[tuple[str, str]], today: dt.date) -> str:
    lines = [
        BEGIN,
        f"_由 `harness/iterate.py` 于 {today.isoformat()} 生成，请勿手工编辑本区块_",
        "",
    ]
    if not items:
        lines.append("- 无待办 🎉")
    for icon, text in items:
        lines.append(f"- [ ] {icon} {text}")
    lines.append(END)
    return "\n".join(lines)


def write_todo(block: str) -> None:
    text = TODO.read_text(encoding="utf-8") if TODO.exists() else "# TODO\n\n"
    if BEGIN in text and END in text:
        pre, rest = text.split(BEGIN, 1)
        post = rest.split(END, 1)[1]
        text = pre + block + post
    else:
        text = text.rstrip() + "\n\n## 自动发现（harness）\n\n" + block + "\n"
    TODO.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只打印不写文件")
    ap.add_argument("--today", help="覆盖今天日期（测试用）YYYY-MM-DD")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    results, items = collect(today)
    block = render(items, today)
    if not args.check:
        write_todo(block)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            json.dumps(
                {
                    "date": today.isoformat(),
                    "gates": {r.name: r.ok for r in results},
                    "todo": [f"{i} {t}" for i, t in items],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(block)
    nxt = items[0][1] if items else "无"
    print(f"\n▶ 下一项任务: {nxt}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
