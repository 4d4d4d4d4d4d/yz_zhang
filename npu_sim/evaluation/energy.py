"""Workload energy report — the missing "E" of PPA, physically grounded.

The platform reported area and static *power*, but never the total *energy* a
workload consumes. This synthesizes it:

  * dynamic energy = Σ per-op dynamic energy over the mapped ops (each now
    Horowitz-grounded via the modules' estimate_energy, SPEC-013);
  * static energy  = total static power × the workload's runtime (drain);
  * total energy, per-module breakdown, energy/op, and a one-line PPA summary
    (area / energy / latency).

Uses the RuleBasedMapper for op→module attribution and a real simulation for
the runtime, so the number is workload-driven, not a hand-picked constant.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.interfaces.operation import IOperation
from npu_sim.mapping import RuleBasedMapper


@dataclass(frozen=True)
class EnergyReport:
    """Total workload energy (pJ) = dynamic (per-op) + static (power × time)."""

    n_ops: int
    dynamic_pj: float
    static_pj: float
    total_pj: float
    per_module_pj: tuple[tuple[str, float], ...]   # module_id → dynamic pJ, desc
    drain_cycles: int
    total_area_um2: float
    summary_text: str = ""

    @property
    def energy_per_op_pj(self) -> float:
        return self.total_pj / self.n_ops if self.n_ops else 0.0


def analyze_energy(
    operations: Sequence[IOperation],
    architecture: IArchitecture,
    max_cycles: int = 100_000,
) -> EnergyReport:
    """Compute the total energy a workload draws on an elaborated architecture.

    Dynamic energy is attributed per op via the Mapper (Horowitz-grounded
    module estimate_energy); static energy is the chip's static power over the
    measured drain time.
    """
    from npu_sim.evaluation.runner import run_simulation

    # Dynamic: map ops → modules, sum per-op dynamic energy (pure, pre-run).
    plan = RuleBasedMapper(strict=False).map(operations, architecture)
    per_mod: dict[str, float] = defaultdict(float)
    for d in plan.decisions:
        per_mod[d.module_id] += d.energy.dynamic_pj
    dynamic_pj = sum(per_mod.values())

    # Static: static power (µW) over the workload runtime (drain, ps).
    result = run_simulation(architecture, max_cycles=max_cycles)
    drain_ps = result.drain_time_ps
    main_clock = architecture.clocks[next(iter(architecture.clocks))]
    drain_cycles = drain_ps // max(1, main_clock.period_ps)
    # W × s: (µW·1e-6) × (ps·1e-12) × 1e12 pJ/J = µW × ps × 1e-6
    static_pj = result.total_static_power_uw * drain_ps * 1e-6

    total_pj = dynamic_pj + static_pj
    per_module = tuple(sorted(per_mod.items(), key=lambda kv: (-kv[1], kv[0])))

    area_mm2 = result.total_area_um2 / 1e6
    lines = [
        f"Workload energy ({len(plan.decisions)} ops):",
        f"  dynamic: {dynamic_pj:,.0f} pJ  (per-op, Horowitz-grounded)",
        f"  static:  {static_pj:,.0f} pJ  ({result.total_static_power_uw:,.0f} µW × "
        f"{drain_cycles:,} cyc)",
        f"  total:   {total_pj:,.0f} pJ  ({total_pj/1000:,.1f} nJ)",
        f"  PPA: area {area_mm2:.3f} mm² | energy {total_pj/1000:,.1f} nJ | "
        f"latency {drain_cycles:,} cyc",
    ]
    return EnergyReport(
        n_ops=len(plan.decisions),
        dynamic_pj=dynamic_pj,
        static_pj=static_pj,
        total_pj=total_pj,
        per_module_pj=per_module,
        drain_cycles=drain_cycles,
        total_area_um2=result.total_area_um2,
        summary_text="\n".join(lines),
    )
