#!/usr/bin/env python3
"""参数校准扫描（REQ-SM-003）：多种子网格扫描，输出 docs/reports/calibration.md 与 JSON。

用法：python3 harness/calibrate.py [--seeds 1,2,3] [--quick]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from signalnet.sim import THRESHOLDS, SimConfig, sweep  # noqa: E402

KEYS = list(THRESHOLDS)

GRIDS = {
    "探索曝光": {
        "explore_ratio": [0.05, 0.1],
        "explore_backfill_max": [1.0, 3.0],
        "explore_budget": [50, 100],
    },
    "晋级节奏": {
        "promote_threshold": [0.6, 0.7, 0.8],
        "round_window_s": [24 * 3600, 72 * 3600],
    },
}


def aggregate(rows: list[dict]) -> dict:
    out = {}
    for k in [*KEYS, "honest_rep", "creator_earnings_share"]:
        vals = [r["metrics"][k] for r in rows]
        out[k] = (round(statistics.mean(vals), 4), round(min(vals), 4), round(max(vals), 4))
    out["pass_rate"] = sum(r["all_pass"] for r in rows) / len(rows)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--quick", action="store_true", help="只跑 4 天、单种子，用于冒烟")
    args = ap.parse_args()
    seeds = [int(x) for x in args.seeds.split(",")]
    base = SimConfig(days=4) if args.quick else SimConfig()
    if args.quick:
        seeds = seeds[:1]
    report: dict = {"base": {k: v for k, v in vars(base).items()}, "seeds": seeds, "grids": {}}
    lines = [
        "# 参数校准报告（REQ-SM-003）",
        "",
        f"由 `harness/calibrate.py` 生成。种子：{seeds}；基础配置见 `signalnet.sim.SimConfig`。",
        "",
        "门槛（REQ-SM-002）：" + "；".join(f"`{k}` {op} {v}" for k, (op, v) in THRESHOLDS.items()),
        "",
        "单元格为 均值 [最小, 最大]；pass_rate = 全部门槛同时满足的种子比例。",
        "注意：仿真中读者每页 10 条，探索位数 = ceil(10×比例×补位上限)，"
        "部分组合取整后等价，结果相同。",
        "",
        "**当前默认**：explore_ratio=0.1、explore_backfill_max=1.0、explore_budget=100、"
        "promote_threshold=0.7、round_window_s=86400（commit 16h）。",
        "",
    ]
    for name, grid in GRIDS.items():
        per: dict[str, list] = {}
        for seed in seeds:
            for row in sweep(replace(base, seed=seed), grid):
                key = json.dumps(row["params"], sort_keys=True)
                per.setdefault(key, []).append(row)
        results = [{"params": json.loads(k), **aggregate(v)} for k, v in per.items()]
        results.sort(key=lambda r: (-r["pass_rate"], r["low_quality_exposure_share"][0]))
        report["grids"][name] = results
        lines += [f"## {name}", ""]
        cols = list(grid)
        lines.append("| " + " | ".join(cols + KEYS + ["pass_rate"]) + " |")
        lines.append("|" + "---|" * (len(cols) + len(KEYS) + 1))
        for r in results:
            cells = [str(r["params"][c]) for c in cols]
            cells += [f"{r[k][0]} [{r[k][1]}, {r[k][2]}]" for k in KEYS]
            cells.append(f"{r['pass_rate']:.0%}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    out_dir = ROOT / "docs" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "calibration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out_dir / "calibration.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
