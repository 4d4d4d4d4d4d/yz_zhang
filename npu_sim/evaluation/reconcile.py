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

    lines = [
        "Estimate vs measured (SPEC-006 §8):",
        f"  ops mapped:      {len(plan.decisions)}"
        + (f"  (unmapped: {list(plan.unmapped)})" if plan.unmapped else ""),
        f"  static estimate: {est:,} cycles (op-serial, no overlap/backpressure)",
        f"  measured drain:  {measured:,} cycles",
        f"  ratio measured/estimate: "
        + (f"{ratio:.2f}×" if ratio == ratio else "n/a"),
        f"  abs error:       {abs_err:+,} cycles",
    ]
    return ReconcileReport(
        plan=plan,
        estimate_cycles=est,
        measured_cycles=measured,
        ratio=ratio,
        abs_error_cycles=abs_err,
        summary_text="\n".join(lines),
    )
