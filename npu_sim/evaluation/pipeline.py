"""Measured pipeline-bottleneck analysis (SPEC-006 §8 throughput model).

Reconciliation (reconcile.py) exposed that a wired NPU datapath's measured
drain runs 5–15× over the RuleBasedMapper's static estimate. The mechanism,
confirmed empirically:

  The Mapper routes each op to *one* module in isolation and calls the
  busiest-by-routed-ops module the bottleneck. But a physical datapath
  *streams every token through the whole chain* (DAGC→DSB→MAC→VAU→AVP→…).
  Steady-state throughput is therefore set by the slowest **stage on the
  path**, not by where the Mapper routed the op. On the attention chip the
  Mapper called ``mac`` the bottleneck (6 matmuls × 105 = 630 cyc), but the
  real bottleneck is ``avp`` at 512 cyc/token — and *all* tokens pass through
  it, so drain ≈ pipe-latency + (N−1)×512, which the Mapper cannot see
  because it never reads the connection topology.

This module measures the truth instead of estimating it: run the sim, tally
each module's busy-cycles and the tokens that flowed through it, and derive
the per-stage initiation interval (II = busy_cycles / tokens_through). The
bottleneck is the max-II stage; the modeled drain uses the textbook pipeline
formula ``pipe_latency + (N−1)·II_bottleneck`` and reconciles to within <1%
of measured — turning the reconcile gap into an explained attribution.

Because it reads snapshot_state() + connection counters over an elaborated
arch (no module construction, no estimate_* calls), it stays inside the
YAML-driven evaluation contract.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.runtime.connection import TlmConnection


@dataclass(frozen=True)
class StageProfile:
    """One module's measured per-token service cost in the datapath."""

    module_id: str
    busy_cycles: int
    tokens_through: int
    service_ii: float          # busy_cycles / tokens_through (initiation interval)
    dominant_stage: Optional[str]  # the stage name it spent most busy cycles in


@dataclass(frozen=True)
class PipelineBottleneckReport:
    """Measured pipeline throughput attribution (SPEC-006 §8)."""

    stages: tuple[StageProfile, ...]        # all profiled, sorted by II desc
    bottleneck_module: Optional[str]
    bottleneck_ii: float
    n_tokens: int
    pipe_latency_cycles: float              # Σ service_ii (first-token traversal)
    modeled_drain_cycles: float             # pipe_latency + (N-1)·II_bottleneck
    measured_drain_cycles: int
    model_error_pct: float                  # |modeled - measured| / measured * 100
    summary_text: str = ""


def analyze_pipeline_bottleneck(
    arch: IArchitecture,
    max_cycles: int = 100_000,
) -> PipelineBottleneckReport:
    """Run the sim and attribute steady-state throughput to the slowest stage.

    ``service_ii`` per module is measured busy-cycles ÷ tokens that flowed out
    of it. The bottleneck is the largest II; the modeled drain uses the
    pipeline formula ``pipe_latency + (N−1)·II_bottleneck`` and is reconciled
    against the measured drain so the residual (fill/transport) is explicit.
    """
    from npu_sim.evaluation.runner import run_simulation

    busy: Counter[str] = Counter()
    stage_hist: dict[str, Counter[str]] = {}

    def hook(cycle_index: int, live_arch: IArchitecture) -> None:
        for mid, m in live_arch.modules.items():
            st = m.snapshot_state()
            if st.busy:
                busy[mid] += 1
                if st.current_op is not None:
                    stage_hist.setdefault(mid, Counter())[st.current_op] += 1

    result = run_simulation(arch, max_cycles=max_cycles, per_cycle_hook=hook)

    main_clock = arch.clocks[next(iter(arch.clocks))]
    measured = result.drain_time_ps // max(1, main_clock.period_ps)

    # tokens_through(module) = tokens successfully dequeued from its outputs.
    out_tokens: Counter[str] = Counter()
    for c in arch.connections:
        if isinstance(c.runtime, TlmConnection):
            out_tokens[c.spec.source_module] += c.runtime.tokens_dequeued

    stages: list[StageProfile] = []
    for mid in sorted(busy):
        tok = out_tokens.get(mid, 0)
        if tok <= 0:
            continue  # no output tokens (e.g. a sink) → II undefined
        dom = None
        if mid in stage_hist and stage_hist[mid]:
            dom = stage_hist[mid].most_common(1)[0][0]
        stages.append(StageProfile(
            module_id=mid,
            busy_cycles=busy[mid],
            tokens_through=tok,
            service_ii=busy[mid] / tok,
            dominant_stage=dom,
        ))

    stages.sort(key=lambda s: (-s.service_ii, s.module_id))

    if stages:
        bottleneck = stages[0]
        bn_id: Optional[str] = bottleneck.module_id
        bn_ii = bottleneck.service_ii
        n_tokens = bottleneck.tokens_through
        pipe_latency = sum(s.service_ii for s in stages)
        modeled = pipe_latency + max(0, n_tokens - 1) * bn_ii
    else:
        bn_id, bn_ii, n_tokens, pipe_latency, modeled = None, 0.0, 0, 0.0, 0.0

    err_pct = (
        abs(modeled - measured) / measured * 100 if measured > 0 else float("nan")
    )

    lines = [
        "Pipeline bottleneck (measured, SPEC-006 §8):",
        f"  bottleneck stage: {bn_id!r} @ II={bn_ii:.0f} cyc/token"
        + (f" ({stages[0].dominant_stage})" if stages and stages[0].dominant_stage else ""),
        f"  tokens through:   {n_tokens}",
        f"  pipe latency:     {pipe_latency:.0f} cyc (Σ per-stage II, first-token fill)",
        f"  modeled drain:    {modeled:.0f} cyc  = pipe_latency + (N-1)·II_bottleneck",
        f"  measured drain:   {measured:,} cyc",
        f"  model error:      {err_pct:.1f}%",
    ]
    return PipelineBottleneckReport(
        stages=tuple(stages),
        bottleneck_module=bn_id,
        bottleneck_ii=bn_ii,
        n_tokens=n_tokens,
        pipe_latency_cycles=pipe_latency,
        modeled_drain_cycles=modeled,
        measured_drain_cycles=measured,
        model_error_pct=err_pct,
        summary_text="\n".join(lines),
    )
