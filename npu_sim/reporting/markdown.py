"""Render SimulationResult / ComparisonReport as Markdown.

Designed to be PR / email-pasteable. No external dependencies.

The renderers are pure functions of the result objects (which themselves
are dataclasses produced by `npu_sim.evaluation`). No re-simulation or
re-elaboration happens here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from npu_sim.evaluation.comparator import ComparisonReport
from npu_sim.evaluation.reconcile import PerOpReconcileReport, ReconcileReport
from npu_sim.evaluation.runner import SimulationResult

if TYPE_CHECKING:
    from npu_sim.evaluation.energy import EnergyReport
    from npu_sim.evaluation.fidelity import ChipFidelityReport
    from npu_sim.evaluation.optimize import OptimizeReport
    from npu_sim.evaluation.pipeline import PipelineBottleneckReport
    from npu_sim.evaluation.snapshot import SnapshotDiff, StateSnapshot
    from npu_sim.evaluation.sweep import SweepReport
from npu_sim.mapping import MappingPlan
from npu_sim.runtime.invariants import InvariantReport


# ============================================================
# Public API
# ============================================================


def render_simulation_report(result: SimulationResult) -> str:
    """Render one SimulationResult as a Markdown document."""
    parts: list[str] = []
    parts.append(_header(result))
    parts.append(_summary_table(result))
    parts.append(_invariants_section(result.invariant_report))
    parts.append(_stall_section(result))
    parts.append(_token_flow_section(result))
    if result.elaboration_warnings:
        parts.append(_elaboration_warnings_section(result.elaboration_warnings))
    return "\n\n".join(p for p in parts if p)


def render_comparison_report(report: ComparisonReport) -> str:
    """Render a baseline-vs-variant comparison as a Markdown document."""
    parts: list[str] = []
    parts.append(_comparison_header(report))
    parts.append(_comparison_summary_table(report))
    parts.append(_bottleneck_callout(report))
    parts.append(_per_module_delta_table(report))
    parts.append(_comparison_invariants_section(report))
    return "\n\n".join(p for p in parts if p)


# ============================================================
# Simulation report sections
# ============================================================


def _header(result: SimulationResult) -> str:
    verdict = "✅ VALID" if result.invariant_report.overall_valid else "❌ INVALID"
    return (
        f"# Simulation Report: {result.architecture_name}\n\n"
        f"**Status:** {verdict}"
    )


def _summary_table(result: SimulationResult) -> str:
    rows = [
        ("drain_time_ps", f"{result.drain_time_ps:,}"),
        ("cycles_run", str(result.cycles_run)),
        ("sim_time_ps", f"{result.sim_time_ps:,}"),
        ("total_stall_ps", f"{result.total_stall_ps:,}"),
        ("bottleneck_module", repr(result.bottleneck_module)),
        ("total_area_um2", f"{result.total_area_um2:.2f}"),
        ("total_static_power_uw", f"{result.total_static_power_uw:.3f}"),
        ("tokens_delivered_total", str(sum(result.tokens_delivered.values()))),
        ("tokens_in_flight_total", str(sum(result.tokens_in_flight.values()))),
    ]
    return "## Summary\n\n" + _two_col_table("Metric", "Value", rows)


def _invariants_section(report: InvariantReport) -> str:
    body = ["## Invariants"]
    if report.failures:
        body.append("### Failures")
        rows = [(f.invariant_id, f.description) for f in report.failures]
        body.append(_two_col_table("ID", "Description", rows))
    if report.warnings:
        body.append("### Warnings")
        rows = [(w.invariant_id, w.description) for w in report.warnings]
        body.append(_two_col_table("ID", "Description", rows))
    if not report.failures and not report.warnings:
        body.append("All invariants passed; no warnings.")
    return "\n\n".join(body)


def _stall_section(result: SimulationResult) -> str:
    if not result.per_module_stall_ps:
        return "## Stall Analysis\n\nNo stalls recorded."
    rows = sorted(
        result.per_module_stall_ps.items(), key=lambda kv: -kv[1]
    )
    rendered = [(m, f"{ps:,}") for m, ps in rows]
    body = "## Stall Analysis\n\n" + _two_col_table(
        "Module", "Stall (ps)", rendered
    )
    if result.bottleneck_module:
        body += f"\n\n**Bottleneck:** `{result.bottleneck_module}`"
    return body


def _token_flow_section(result: SimulationResult) -> str:
    if not result.tokens_delivered:
        return ""
    rows = [
        (
            conn,
            f"{result.tokens_delivered[conn]:,}",
            f"{result.tokens_in_flight.get(conn, 0):,}",
        )
        for conn in sorted(result.tokens_delivered)
    ]
    body = ["## Token Flow", _three_col_table(
        "Connection", "Delivered", "In-flight", rows
    )]
    return "\n\n".join(body)


def _elaboration_warnings_section(warnings: Iterable[str]) -> str:
    items = "\n".join(f"- {w}" for w in warnings)
    return f"## Elaboration Warnings\n\n{items}"


# ============================================================
# Comparison report sections
# ============================================================


def _comparison_header(report: ComparisonReport) -> str:
    verdict = "✅ VALID" if report.both_valid else "❌ INVALID"
    return (
        f"# Comparison: `{report.baseline.architecture_name}` "
        f"→ `{report.variant.architecture_name}`\n\n"
        f"**Status:** {verdict}"
    )


def _comparison_summary_table(report: ComparisonReport) -> str:
    b = report.baseline
    v = report.variant

    def _fmt_pct(p: float) -> str:
        return f"{p:+.1f}%" if p == p else "n/a"  # NaN-safe

    rows = [
        (
            "drain_time_ps",
            f"{b.drain_time_ps:,}",
            f"{v.drain_time_ps:,}",
            f"{report.drain_time_delta_ps:+,} ({_fmt_pct(report.drain_time_delta_pct)})",
        ),
        (
            "cycles_run",
            str(b.cycles_run),
            str(v.cycles_run),
            f"{report.cycle_delta:+d} ({_fmt_pct(report.cycle_delta_pct)})",
        ),
        (
            "total_stall_ps",
            f"{b.total_stall_ps:,}",
            f"{v.total_stall_ps:,}",
            f"{report.stall_delta_ps:+,}",
        ),
        (
            "bottleneck_module",
            repr(b.bottleneck_module),
            repr(v.bottleneck_module),
            "CHANGED" if report.bottleneck_changed else "—",
        ),
        (
            "total_area_um2",
            f"{b.total_area_um2:.2f}",
            f"{v.total_area_um2:.2f}",
            f"{report.area_delta_um2:+.2f}",
        ),
        (
            "static_power_uw",
            f"{b.total_static_power_uw:.3f}",
            f"{v.total_static_power_uw:.3f}",
            f"{report.static_power_delta_uw:+.3f}",
        ),
    ]
    return "## Summary\n\n" + _four_col_table(
        "Metric", "Baseline", "Variant", "Δ", rows
    )


def _bottleneck_callout(report: ComparisonReport) -> str:
    if not report.bottleneck_changed:
        return ""
    return (
        "## Bottleneck Change\n\n"
        f"`{report.baseline_bottleneck}` → `{report.variant_bottleneck}`"
    )


def _per_module_delta_table(report: ComparisonReport) -> str:
    if not report.per_module_stall_delta_ps:
        return ""
    rows = sorted(
        (
            (m, report.baseline.per_module_stall_ps.get(m, 0),
             report.variant.per_module_stall_ps.get(m, 0), d)
            for m, d in report.per_module_stall_delta_ps.items()
        ),
        key=lambda r: -abs(r[3]),
    )
    rendered = [
        (m, f"{b:,}", f"{v:,}", f"{d:+,}")
        for m, b, v, d in rows
        if not (b == 0 and v == 0)
    ]
    if not rendered:
        return ""
    return "## Per-module Stall Delta\n\n" + _four_col_table(
        "Module", "Baseline (ps)", "Variant (ps)", "Δ (ps)", rendered
    )


def _comparison_invariants_section(report: ComparisonReport) -> str:
    lines = ["## Invariants"]
    b_valid = report.baseline.invariant_report.overall_valid
    v_valid = report.variant.invariant_report.overall_valid
    lines.append(
        f"- Baseline: {'✅ VALID' if b_valid else '❌ INVALID'}"
    )
    lines.append(
        f"- Variant:  {'✅ VALID' if v_valid else '❌ INVALID'}"
    )

    if not b_valid:
        lines.append("")
        lines.append("### Baseline Failures")
        for f in report.baseline.invariant_report.failures:
            lines.append(f"- **{f.invariant_id}**: {f.description}")
    if not v_valid:
        lines.append("")
        lines.append("### Variant Failures")
        for f in report.variant.invariant_report.failures:
            lines.append(f"- **{f.invariant_id}**: {f.description}")
    return "\n".join(lines)


def render_mapping_report(plan: MappingPlan, arch_name: str = "") -> str:
    """Render a Mapper MappingPlan (SPEC-006) as Markdown.

    Shows the op→module routing, per-op latency/energy, aggregate static
    estimate, and any unmapped ops. Pure function of the plan.
    """
    parts: list[str] = []
    title = f"Mapping estimate — `{arch_name}`" if arch_name else "Mapping estimate"
    parts.append(f"# {title}")

    n = len(plan.decisions)
    status = "✅ all ops mapped" if not plan.unmapped else (
        f"⚠️ {len(plan.unmapped)} op(s) unmapped"
    )
    rows = [
        ("ops mapped", str(n)),
        ("op-serial cycles (sum)", f"{plan.total_typical_cycles:,}"),
    ]
    if plan.bottleneck_module:
        rows.append((
            "bottleneck cycles",
            f"{plan.bottleneck_cycles:,} (busiest module `{plan.bottleneck_module}`)",
        ))
    rows += [
        ("total dynamic energy", f"{plan.total_dynamic_pj:,.1f} pJ"),
        ("status", status),
    ]
    parts.append(_two_col_table("Metric", "Value", rows))

    if plan.decisions:
        rows = []
        for d in plan.decisions:
            alts = ", ".join(d.alternatives) if d.alternatives else "—"
            rows.append((
                str(d.op_index),
                f"`{d.op_type}`",
                f"**{d.module_id}**",
                f"{d.latency.typical_cycles} cyc",
                f"{d.energy.dynamic_pj:.1f} pJ",
                alts,
            ))
        lines = [
            "| # | op | → module | latency | energy | alternatives |",
            "|---|---|---|---:|---:|---|",
        ]
        for r in rows:
            lines.append("| " + " | ".join(r) + " |")
        parts.append("## Routing\n\n" + "\n".join(lines))

    if plan.unmapped:
        parts.append(
            "## Unmapped ops\n\n"
            + ", ".join(str(i) for i in plan.unmapped)
            + "\n\n> No module's active capabilities cover these ops' "
            "required capabilities."
        )

    return "\n\n".join(parts)


def render_reconcile_report(
    chain: ReconcileReport,
    per_op: Optional[PerOpReconcileReport] = None,
    arch_name: str = "",
) -> str:
    """Render an estimate-vs-measured reconciliation (SPEC-006 §8) as Markdown.

    Shows both static estimates (op-serial sum and bottleneck), the measured
    drain, the two ratios, and — if ``per_op`` is given — the per-op table.
    """
    parts: list[str] = []
    title = f"Estimate vs measured — `{arch_name}`" if arch_name else "Estimate vs measured"
    parts.append(f"# {title}")

    plan = chain.plan
    def _r(x: float) -> str:
        return f"{x:.2f}×" if x == x else "n/a"
    bn_ratio = (
        chain.measured_cycles / plan.bottleneck_cycles
        if plan.bottleneck_cycles > 0 else float("nan")
    )
    parts.append(_two_col_table("Metric", "Value", [
        ("ops mapped", str(len(plan.decisions))
            + (f" (unmapped: {list(plan.unmapped)})" if plan.unmapped else "")),
        ("op-serial estimate", f"{chain.estimate_cycles:,} cyc (sum, no overlap)"),
        ("bottleneck estimate",
            f"{plan.bottleneck_cycles:,} cyc (busiest module `{plan.bottleneck_module}`)"),
        ("measured drain", f"{chain.measured_cycles:,} cyc"),
        ("ratio measured / op-serial", _r(chain.ratio)),
        ("ratio measured / bottleneck", _r(bn_ratio)),
    ]))

    if plan.per_module_cycles:
        rows = [(f"`{mid}`", f"{cyc:,} cyc") for mid, cyc in plan.per_module_cycles]
        parts.append("## Per-module serial work\n\n"
                     + _two_col_table("module", "serial cycles", rows))

    if per_op is not None and per_op.rows:
        lines = [
            "| # | op | module | est cyc | measured cyc | ratio |",
            "|---|---|---|---:|---:|---:|",
        ]
        for r in per_op.rows:
            rr = f"{r.ratio:.2f}×" if r.ratio == r.ratio else "n/a"
            lines.append(
                f"| {r.op_index} | `{r.op_type}` | **{r.module_id}** | "
                f"{r.estimate_cycles} | {r.measured_cycles} | {rr} |"
            )
        parts.append("## Per-op estimate vs measured\n\n" + "\n".join(lines))
        parts.append(
            "> Steady-state measured cycles are the sink inter-arrival gap — the "
            "pipeline throughput period, set by the busiest stage, not each op's "
            "own latency."
        )

    return "\n\n".join(parts)


def render_state_snapshot(snap: "StateSnapshot", arch_name: str = "") -> str:
    """Render a whole-chip StateSnapshot (QEMU §3.2 savevm data view) as Markdown.

    Shows the cycle/time, every module's busy/stage/stall state, and every
    connection's FIFO occupancy — the read-only half of a checkpoint.
    """
    name = arch_name or snap.architecture_name
    title = f"Chip state snapshot — `{name}`" if name else "Chip state snapshot"
    parts: list[str] = [f"# {title}"]

    parts.append(_two_col_table("Metric", "Value", [
        ("cycle", f"{snap.cycle:,}"),
        ("sim time", f"{snap.time_ps:,} ps"),
        ("busy modules", f"{len(snap.busy_modules())} / {len(snap.modules)}"),
        ("tokens in flight", str(snap.total_in_flight())),
    ]))

    mod_lines = [
        "| module | type | busy | stage | fifos | stall |",
        "|---|---|:-:|---|---|---|",
    ]
    for m in snap.modules:
        fifos = ", ".join(f"{k}={v}" for k, v in m.internal_fifo_levels) or "—"
        mod_lines.append(
            f"| `{m.module_id}` | {m.module_type} | {'●' if m.busy else '·'} | "
            f"{m.current_op or '—'} | {fifos} | {m.last_stall_reason or '—'} |"
        )
    parts.append("## Modules\n\n" + "\n".join(mod_lines))

    if snap.connections:
        conn_lines = [
            "| connection | in-flight | capacity | util | dequeued |",
            "|---|---:|---:|---:|---:|",
        ]
        for c in snap.connections:
            conn_lines.append(
                f"| `{c.key}` | {c.in_flight} | {c.capacity} | "
                f"{c.utilization * 100:.0f}% | {c.tokens_dequeued} |"
            )
        parts.append("## Connection FIFOs\n\n" + "\n".join(conn_lines))

    return "\n\n".join(parts)


def render_optimize_report(report: "OptimizeReport") -> str:
    """Render a greedy bottleneck-chasing optimization as Markdown."""
    parts: list[str] = [f"# Bottleneck optimization — `{report.base_name}`"]
    parts.append(_two_col_table("Metric", "Value", [
        ("knobs", ", ".join(f"`{k}`" for k in report.knobs)),
        ("initial drain", f"{report.initial_drain_cycles:,} cyc"),
        ("final drain", f"{report.final_drain_cycles:,} cyc"),
        ("improvement", f"{report.drain_improvement_pct:+.0f}%"),
        ("stop reason", report.stop_reason),
    ]))

    lines = [
        "| round | knob | change | drain (cyc) | bottleneck | kept |",
        "|---:|---|---|---:|---|:-:|",
    ]
    for s in report.steps:
        lines.append(
            f"| {s.round_index} | `{s.knob}` | {s.from_value}→{s.to_value} | "
            f"{s.drain_cycles:,} | `{s.bottleneck_module}` | "
            f"{'✓' if s.accepted else '✗'} |"
        )
    parts.append("## Search trace\n\n" + "\n".join(lines))

    parts.append(
        f"**Final design:** `{report.final_selection}` — "
        f"{report.drain_improvement_pct:+.0f}% drain vs the initial config. "
        "Each round widened the current bottleneck stage; the search stopped "
        "when widening stopped paying off."
    )
    parts.append(_AREA_MODEL_CAVEAT)
    return "\n\n".join(parts)


def render_sweep_report(report: "SweepReport") -> str:
    """Render a design-space sweep (PPA vs one config knob) as Markdown."""
    parts: list[str] = [f"# Design-space sweep — `{report.param_path}`"]
    parts.append(f"Base: `{report.base_name}`")

    base = report.baseline_drain_cycles
    lines = [
        "| value | drain (cyc) | Δ drain | area (um²) | static µW | bottleneck |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for p in report.points:
        dpct = (p.drain_cycles - base) / base * 100 if base else 0.0
        best = " ⭐" if p.value == report.best_value else ""
        lines.append(
            f"| {p.value}{best} | {p.drain_cycles:,} | {dpct:+.0f}% | "
            f"{p.total_area_um2:,.0f} | {p.static_power_uw:,.0f} | "
            f"`{p.bottleneck_module}`@{p.bottleneck_ii:.0f} |"
        )
    parts.append("\n".join(lines))

    if report.bottleneck_shifted:
        parts.append(
            "> ⚠ The bottleneck **shifted** during the sweep: once the swept "
            "stage is no longer the slowest, widening it further yields "
            "diminishing returns — chase the new bottleneck instead."
        )
    else:
        parts.append(
            f"> Best drain at `{report.param_path}` = {report.best_value}. "
            "The bottleneck stayed on the same module across the sweep."
        )
    parts.append(_AREA_MODEL_CAVEAT)
    return "\n\n".join(parts)


# Area is capability-presence-based, not size-based (see
# test_area_model_sensitivity.py / docs/specs/README.md). Scaling knobs
# (array size, lanes, buffer_kb, vector_width) are modeled area-free, so a
# flat area column across such a sweep is a known model gap, not a real
# "free" speed-up. Surfaced in reports so results aren't misread.
_AREA_MODEL_CAVEAT = (
    "> ℹ️ **Area caveat:** the area model sums active-capability costs and is "
    "currently *size-blind* — scaling knobs (array size, lanes, buffer, vector "
    "width) are modeled as area-free, so a flat area column is a known gap "
    "(Phase 5 calibration), not a real zero-cost win."
)


def render_energy_report(report: "EnergyReport", arch_name: str = "") -> str:
    """Render a workload energy report (dynamic + static → total) as Markdown."""
    title = f"Workload energy — `{arch_name}`" if arch_name else "Workload energy"
    parts: list[str] = [f"# {title}"]
    parts.append(_two_col_table("Metric", "Value", [
        ("ops", str(report.n_ops)),
        ("dynamic energy", f"{report.dynamic_pj:,.0f} pJ"),
        ("static energy", f"{report.static_pj:,.0f} pJ"),
        ("total energy", f"{report.total_pj:,.0f} pJ ({report.total_pj/1000:,.1f} nJ)"),
        ("energy / op", f"{report.energy_per_op_pj:,.0f} pJ"),
        ("area", f"{report.total_area_um2/1e6:.3f} mm²"),
        ("latency", f"{report.drain_cycles:,} cyc"),
    ]))
    if report.per_module_pj:
        rows = [
            (f"`{mid}`", f"{pj:,.0f} pJ",
             f"{(pj / report.dynamic_pj * 100.0) if report.dynamic_pj else 0:.0f}%")
            for mid, pj in report.per_module_pj
        ]
        parts.append("## Dynamic energy by module\n\n"
                     + _three_col_table("module", "dynamic pJ", "share", rows))
    parts.append(
        "> Dynamic = Σ per-op energy (Horowitz-grounded, SPEC-013); static = "
        "chip static power × runtime. Absolute figures carry the ±30% "
        "analytical band (see docs/Physical-Validation.md)."
    )
    return "\n\n".join(parts)


def render_fidelity_report(report: "ChipFidelityReport", arch_name: str = "") -> str:
    """Render a chip PPA-fidelity breakdown (physical vs placeholder) as Markdown."""
    title = f"Chip PPA fidelity — `{arch_name}`" if arch_name else "Chip PPA fidelity"
    parts: list[str] = [f"# {title}"]
    parts.append(_two_col_table("Metric", "Value", [
        ("area on grounded models", f"{report.grounded_pct:.0f}%"),
        ("total area", f"{report.total_area_um2:,.0f} µm²"),
        ("grounded area", f"{report.grounded_area_um2:,.0f} µm²"),
    ]))

    badge = {"physical": "✅ physical", "hybrid": "🟡 hybrid",
             "placeholder": "⚠ placeholder"}
    lines = [
        "| module | type | area (µm²) | area % | status |",
        "|---|---|---:|---:|---|",
    ]
    for m in report.modules:
        pct = (m.area_um2 / report.total_area_um2 * 100.0) if report.total_area_um2 else 0.0
        lines.append(
            f"| `{m.module_id}` | {m.module_type} | {m.area_um2:,.0f} | "
            f"{pct:.0f}% | {badge.get(m.status, m.status)} |"
        )
    parts.append("## Per-module\n\n" + "\n".join(lines))
    parts.append(
        "> **physical** = SPEC-013 literature-grounded (scales with size); "
        "**placeholder** = `[calibration knob]`, awaiting Phase-5 synthesis "
        "(control-plane FSM logic). Absolute figures carry the SPEC-013 ±30% "
        "analytical band pending calibration."
    )
    return "\n\n".join(parts)


def render_pipeline_bottleneck(
    report: "PipelineBottleneckReport", arch_name: str = ""
) -> str:
    """Render a measured pipeline-bottleneck attribution (SPEC-006 §8)."""
    title = f"Pipeline bottleneck — `{arch_name}`" if arch_name else "Pipeline bottleneck"
    parts: list[str] = [f"# {title}"]

    parts.append(_two_col_table("Metric", "Value", [
        ("bottleneck stage",
            f"`{report.bottleneck_module}` @ II={report.bottleneck_ii:.0f} cyc/token"),
        ("tokens through", str(report.n_tokens)),
        ("pipe latency (fill)", f"{report.pipe_latency_cycles:.0f} cyc"),
        ("modeled drain", f"{report.modeled_drain_cycles:.0f} cyc"),
        ("measured drain", f"{report.measured_drain_cycles:,} cyc"),
        ("model error", f"{report.model_error_pct:.1f}%"),
    ]))

    if report.stages:
        lines = [
            "| stage (module) | dominant | busy cyc | tokens | II (cyc/tok) |",
            "|---|---|---:|---:|---:|",
        ]
        for i, s in enumerate(report.stages):
            marker = " ⟵ bottleneck" if i == 0 else ""
            lines.append(
                f"| `{s.module_id}`{marker} | {s.dominant_stage or '—'} | "
                f"{s.busy_cycles:,} | {s.tokens_through} | {s.service_ii:.0f} |"
            )
        parts.append("## Per-stage service time\n\n" + "\n".join(lines))
        parts.append(
            "> Modeled drain = Σ per-stage II (first-token fill) + (N−1)·II_bottleneck. "
            "Every token streams through every stage, so throughput is set by the "
            "slowest stage on the path — not by where a Mapper routes the op."
        )

    return "\n\n".join(parts)


def render_snapshot_diff(diff: "SnapshotDiff") -> str:
    """Render a SnapshotDiff (two whole-chip states at a cycle) as Markdown."""
    parts: list[str] = ["# Chip state diff"]
    parts.append(_two_col_table("side", "architecture / cycle", [
        ("A", f"`{diff.name_a}` @ cycle {diff.cycle_a:,}"),
        ("B", f"`{diff.name_b}` @ cycle {diff.cycle_b:,}"),
    ]))

    if diff.cycle_a != diff.cycle_b:
        parts.append(
            f"> ⚠ compared at different cycles ({diff.cycle_a} vs {diff.cycle_b}) — "
            "one side drained earlier."
        )

    if diff.identical:
        parts.append("**Chip state is identical.**")
        return "\n\n".join(parts)

    if diff.only_in_a or diff.only_in_b:
        parts.append(_two_col_table("only in A", "only in B", [
            (", ".join(f"`{m}`" for m in diff.only_in_a) or "—",
             ", ".join(f"`{m}`" for m in diff.only_in_b) or "—"),
        ]))

    if diff.module_diffs:
        rows = [
            (f"`{d.entity}`", d.field, f"`{d.value_a}`", f"`{d.value_b}`")
            for d in diff.module_diffs
        ]
        parts.append("## Module state differences\n\n"
                     + _four_col_table("module", "field", "A", "B", rows))

    if diff.connection_diffs:
        rows = [
            (f"`{d.entity}`", d.field, f"`{d.value_a}`", f"`{d.value_b}`")
            for d in diff.connection_diffs
        ]
        parts.append("## Connection FIFO differences\n\n"
                     + _four_col_table("connection", "field", "A", "B", rows))

    return "\n\n".join(parts)


# ============================================================
# Table helpers
# ============================================================


def _two_col_table(h1: str, h2: str, rows: Iterable[tuple[str, str]]) -> str:
    lines = [f"| {h1} | {h2} |", "|---|---|"]
    for c1, c2 in rows:
        lines.append(f"| {c1} | {c2} |")
    return "\n".join(lines)


def _three_col_table(
    h1: str, h2: str, h3: str, rows: Iterable[tuple[str, str, str]]
) -> str:
    lines = [f"| {h1} | {h2} | {h3} |", "|---|---|---|"]
    for c1, c2, c3 in rows:
        lines.append(f"| {c1} | {c2} | {c3} |")
    return "\n".join(lines)


def _four_col_table(
    h1: str, h2: str, h3: str, h4: str, rows: Iterable[tuple[str, str, str, str]]
) -> str:
    lines = [f"| {h1} | {h2} | {h3} | {h4} |", "|---|---|---|---|"]
    for c1, c2, c3, c4 in rows:
        lines.append(f"| {c1} | {c2} | {c3} | {c4} |")
    return "\n".join(lines)
