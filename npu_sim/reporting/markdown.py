"""Render SimulationResult / ComparisonReport as Markdown.

Designed to be PR / email-pasteable. No external dependencies.

The renderers are pure functions of the result objects (which themselves
are dataclasses produced by `npu_sim.evaluation`). No re-simulation or
re-elaboration happens here.
"""

from __future__ import annotations

from typing import Iterable, Optional

from npu_sim.evaluation.comparator import ComparisonReport
from npu_sim.evaluation.runner import SimulationResult
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
