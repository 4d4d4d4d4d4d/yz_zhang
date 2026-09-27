"""Estimate-vs-measured reconciliation. SPEC-006 §8 candidate.

The RuleBasedMapper produces a *static* estimate of an operator trace's
total cycles (sum of per-op estimate_latency). A simulation produces the
*dynamic* measured drain_time. This module joins them: given a trace and
an architecture, compute both and report the gap.

The static estimate assumes op-serial execution with no pipeline overlap
and no back-pressure, so it is a lower bound on the dynamic drain in a
serialised pipeline. The reconciliation quantifies how far measured
diverges from estimate — the basis for calibrating the estimate model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.interfaces.operation import IOperation
from npu_sim.mapping import MappingPlan, RuleBasedMapper


@dataclass(frozen=True)
class ReconcileReport:
    """Static Mapper estimate vs dynamic simulation measurement."""

    plan: MappingPlan
    estimate_cycles: int          # sum of per-op typical_cycles (op-serial)
    measured_cycles: int          # drain_time_ps // clock_period_ps
    ratio: float                  # measured / estimate (NaN if estimate=0)
    abs_error_cycles: int         # measured - estimate
    summary_text: str = ""


@dataclass(frozen=True)
class PerOpRow:
    """One op's static estimate vs its measured sink inter-arrival."""

    op_index: int
    op_type: str
    module_id: str
    estimate_cycles: int          # Mapper's typical_cycles for this op
    measured_cycles: int          # sink inter-arrival gap (steady-state throughput)
    ratio: float                  # measured / estimate (NaN if estimate=0)


@dataclass(frozen=True)
class PerOpReconcileReport:
    """Per-op estimate-vs-measured join (SPEC-006 §8 v1.1)."""

    rows: tuple[PerOpRow, ...]
    summary_text: str = ""


def reconcile(
    operations: Sequence[IOperation],
    architecture: IArchitecture,
    measured_drain_ps: int,
    clock_period_ps: int,
    strict: bool = False,
) -> ReconcileReport:
    """Join a static Mapper estimate with a measured drain time.

    ``measured_drain_ps`` comes from a SimulationResult.drain_time_ps of a
    run driven by the *same* operator trace. ``clock_period_ps`` converts it
    to cycles for an apples-to-apples comparison with the Mapper's
    cycle-domain estimate.
    """
    plan: MappingPlan = RuleBasedMapper(strict=strict).map(operations, architecture)
    est = plan.total_typical_cycles
    measured = measured_drain_ps // max(1, clock_period_ps)
    ratio = (measured / est) if est > 0 else float("nan")
    abs_err = measured - est

    bn = plan.bottleneck_cycles
    bn_ratio = (measured / bn) if bn > 0 else float("nan")
    lines = [
        "Estimate vs measured (SPEC-006 §8):",
        f"  ops mapped:      {len(plan.decisions)}"
        + (f"  (unmapped: {list(plan.unmapped)})" if plan.unmapped else ""),
        f"  op-serial est:   {est:,} cycles (sum, no overlap/backpressure)",
        f"  bottleneck est:  {bn:,} cycles "
        f"(busiest module {plan.bottleneck_module!r}, models module overlap)",
        f"  measured drain:  {measured:,} cycles",
        f"  ratio measured/op-serial:  "
        + (f"{ratio:.2f}×" if ratio == ratio else "n/a"),
        f"  ratio measured/bottleneck: "
        + (f"{bn_ratio:.2f}×" if bn_ratio == bn_ratio else "n/a"),
        f"  abs error (op-serial):     {abs_err:+,} cycles",
    ]
    return ReconcileReport(
        plan=plan,
        estimate_cycles=est,
        measured_cycles=measured,
        ratio=ratio,
        abs_error_cycles=abs_err,
        summary_text="\n".join(lines),
    )


def sink_op_arrivals(architecture: IArchitecture, sink_id: str) -> list[tuple[int, int]]:
    """Extract (op_index, arrival_ps) pairs from a sink Consumer's received
    tokens. Trace tokens carry ``op_index`` in metadata (SPEC-012), preserved
    by every downstream module's ``{**metadata, ...}`` spread, so the sink
    sees the original op index alongside the final arrival timestamp.

    Ordered by arrival time; tokens without an op_index are skipped.
    """
    sink = architecture.modules[sink_id]
    toks = getattr(sink, "received_tokens", None)
    if toks is None:
        raise ValueError(f"module {sink_id!r} does not expose received_tokens")
    pairs = [
        (int(t.metadata["op_index"]), int(t.timestamp_ps))
        for t in toks
        if "op_index" in t.metadata
    ]
    pairs.sort(key=lambda p: p[1])
    return pairs


def reconcile_per_op(
    operations: Sequence[IOperation],
    architecture: IArchitecture,
    arrivals: Sequence[tuple[int, int]],
    clock_period_ps: int,
    strict: bool = False,
) -> PerOpReconcileReport:
    """Per-op estimate-vs-measured join (SPEC-006 §8 v1.1).

    ``arrivals`` = (op_index, arrival_ps) at the sink (see
    :func:`sink_op_arrivals`). The measured per-op cost is the sink
    inter-arrival gap — in a steady-state pipeline this is the throughput
    period, the fair per-op counterpart to the Mapper's op latency estimate.
    The first op's measured cost is its absolute arrival (fill + its own
    latency).
    """
    plan: MappingPlan = RuleBasedMapper(strict=strict).map(operations, architecture)
    est_by_op = {d.op_index: d for d in plan.decisions}

    # arrival_ps keyed by op_index, in arrival order.
    ordered = sorted(arrivals, key=lambda p: p[1])
    rows: list[PerOpRow] = []
    prev_ps = 0
    for pos, (op_index, arr_ps) in enumerate(ordered):
        gap_ps = arr_ps - prev_ps
        prev_ps = arr_ps
        measured_cyc = gap_ps // max(1, clock_period_ps)
        d = est_by_op.get(op_index)
        est_cyc = d.latency.typical_cycles if d else 0
        mod_id = d.module_id if d else "?"
        op_type = d.op_type if d else "?"
        ratio = (measured_cyc / est_cyc) if est_cyc > 0 else float("nan")
        rows.append(PerOpRow(
            op_index=op_index,
            op_type=op_type,
            module_id=mod_id,
            estimate_cycles=est_cyc,
            measured_cycles=measured_cyc,
            ratio=ratio,
        ))

    lines = ["Per-op estimate vs measured (SPEC-006 §8 v1.1):",
             "  op | type | module | est cyc | measured cyc | ratio"]
    for r in rows:
        rr = f"{r.ratio:.2f}×" if r.ratio == r.ratio else "n/a"
        lines.append(
            f"  {r.op_index:>2} | {r.op_type:<8} | {r.module_id:<6} | "
            f"{r.estimate_cycles:>7} | {r.measured_cycles:>12} | {rr}"
        )
    return PerOpReconcileReport(rows=tuple(rows), summary_text="\n".join(lines))
