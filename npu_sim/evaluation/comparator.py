"""Compare two SimulationResults: baseline vs variant.

Produces a `ComparisonReport` capturing deltas in cycles, stall time,
bottleneck, area, and power. Intentionally value-neutral: deltas are
signed numbers; interpretation is left to the caller / report renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from npu_sim.evaluation.runner import SimulationResult


@dataclass(frozen=True)
class ComparisonReport:
    baseline: SimulationResult
    variant: SimulationResult

    cycle_delta: int                       # variant - baseline (positive = slower)
    cycle_delta_pct: float                 # vs baseline (None if baseline=0)
    drain_time_delta_ps: int               # primary latency metric (positive = slower)
    drain_time_delta_pct: float            # vs baseline (NaN if baseline=0)
    stall_delta_ps: int
    bottleneck_changed: bool
    baseline_bottleneck: Optional[str]
    variant_bottleneck: Optional[str]
    area_delta_um2: float
    static_power_delta_uw: float
    per_module_stall_delta_ps: dict[str, int] = field(default_factory=dict)
    both_valid: bool = True
    summary_text: str = ""


def compare(
    baseline: SimulationResult,
    variant: SimulationResult,
) -> ComparisonReport:
    cycle_delta = variant.cycles_run - baseline.cycles_run
    cycle_pct = (
        100.0 * cycle_delta / baseline.cycles_run
        if baseline.cycles_run > 0 else float("nan")
    )
    drain_delta = variant.drain_time_ps - baseline.drain_time_ps
    drain_pct = (
        100.0 * drain_delta / baseline.drain_time_ps
        if baseline.drain_time_ps > 0 else float("nan")
    )
    stall_delta = variant.total_stall_ps - baseline.total_stall_ps
    area_delta = variant.total_area_um2 - baseline.total_area_um2
    power_delta = variant.total_static_power_uw - baseline.total_static_power_uw

    all_module_ids = set(baseline.per_module_stall_ps) | set(variant.per_module_stall_ps)
    per_module_delta = {
        m: variant.per_module_stall_ps.get(m, 0) - baseline.per_module_stall_ps.get(m, 0)
        for m in all_module_ids
    }

    bottleneck_changed = baseline.bottleneck_module != variant.bottleneck_module
    both_valid = (
        baseline.invariant_report.overall_valid
        and variant.invariant_report.overall_valid
    )

    summary = _format_summary(
        baseline=baseline,
        variant=variant,
        cycle_delta=cycle_delta,
        cycle_pct=cycle_pct,
        drain_delta=drain_delta,
        drain_pct=drain_pct,
        stall_delta=stall_delta,
        area_delta=area_delta,
        power_delta=power_delta,
        bottleneck_changed=bottleneck_changed,
        both_valid=both_valid,
    )

    return ComparisonReport(
        baseline=baseline,
        variant=variant,
        cycle_delta=cycle_delta,
        cycle_delta_pct=cycle_pct,
        drain_time_delta_ps=drain_delta,
        drain_time_delta_pct=drain_pct,
        stall_delta_ps=stall_delta,
        bottleneck_changed=bottleneck_changed,
        baseline_bottleneck=baseline.bottleneck_module,
        variant_bottleneck=variant.bottleneck_module,
        area_delta_um2=area_delta,
        static_power_delta_uw=power_delta,
        per_module_stall_delta_ps=per_module_delta,
        both_valid=both_valid,
        summary_text=summary,
    )


# ============================================================
# formatting
# ============================================================


def _format_summary(
    *,
    baseline: SimulationResult,
    variant: SimulationResult,
    cycle_delta: int,
    cycle_pct: float,
    drain_delta: int,
    drain_pct: float,
    stall_delta: int,
    area_delta: float,
    power_delta: float,
    bottleneck_changed: bool,
    both_valid: bool,
) -> str:
    valid_tag = "VALID" if both_valid else "INVALID (see invariant reports)"
    lines = [
        f"Comparison: {baseline.architecture_name!r} (baseline) "
        f"vs {variant.architecture_name!r} (variant) — {valid_tag}",
        f"  drain_time:   {baseline.drain_time_ps} ps → {variant.drain_time_ps} ps "
        f"(Δ={drain_delta:+d}{f', {drain_pct:+.1f}%' if drain_pct == drain_pct else ''})",
        f"  cycles_run:   {baseline.cycles_run} → {variant.cycles_run} "
        f"(Δ={cycle_delta:+d}{f', {cycle_pct:+.1f}%' if cycle_pct == cycle_pct else ''})",
        f"  total_stall:  {baseline.total_stall_ps} ps → "
        f"{variant.total_stall_ps} ps (Δ={stall_delta:+d} ps)",
        f"  bottleneck:   {baseline.bottleneck_module!r} → "
        f"{variant.bottleneck_module!r}"
        + (" (CHANGED)" if bottleneck_changed else ""),
        f"  area:         {baseline.total_area_um2:.1f} um² → "
        f"{variant.total_area_um2:.1f} um² (Δ={area_delta:+.1f})",
        f"  static_power: {baseline.total_static_power_uw:.2f} uW → "
        f"{variant.total_static_power_uw:.2f} uW (Δ={power_delta:+.2f})",
    ]
    return "\n".join(lines)
