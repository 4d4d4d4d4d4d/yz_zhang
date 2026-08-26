"""Greedy bottleneck-chasing design optimizer (SPEC-003 §7 R7 automation).

`sweep` showed the law: widen the limiting stage until the bottleneck shifts,
then chase the new one. This automates that loop. Given a base chip and a set
of config knobs (each a module field with an ascending list of candidate
settings, cheap→wide), it repeatedly:

  1. measures the current pipeline bottleneck (evaluation/pipeline.py),
  2. picks a knob that widens the bottleneck *module* and still has headroom,
  3. bumps it one notch and re-measures,
  4. keeps the change only if drain strictly improves — else stops.

It converges when the bottleneck stage has no remaining knob, or widening it
no longer helps (the classic diminishing-returns wall). The search is greedy
and deterministic — one knob per round, knobs tried in sorted order — so the
same inputs always yield the same design. It is not exhaustive (no
backtracking across knob combinations); that is an honest v1.1 upgrade path.

Every measurement is a real simulation of a real override written on top of
the untouched base — fully YAML-driven, no Python module construction, no
estimate_* calls.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass(frozen=True)
class OptimizeStep:
    """One accepted (or terminal rejected) move in the greedy search."""

    round_index: int
    knob: str                       # "<module_id>.<config_key>"
    from_value: object
    to_value: object
    drain_cycles: int
    bottleneck_module: Optional[str]
    total_area_um2: float
    accepted: bool                  # False = tried, no improvement, search stopped
    total_energy_pj: Optional[float] = None


@dataclass(frozen=True)
class OptimizeReport:
    """Result of a greedy bottleneck-chasing search."""

    base_name: str
    knobs: tuple[str, ...]
    initial_drain_cycles: int
    final_drain_cycles: int
    initial_selection: dict
    final_selection: dict
    steps: tuple[OptimizeStep, ...]
    stop_reason: str
    objective: str = "drain"          # "drain" | "energy" | "edp"
    summary_text: str = ""

    @property
    def drain_improvement_pct(self) -> float:
        if self.initial_drain_cycles <= 0:
            return 0.0
        return (
            (self.initial_drain_cycles - self.final_drain_cycles)
            / self.initial_drain_cycles * 100
        )


def _measure(base_abs: str, selection: dict, max_cycles: int, ops=None, period_ps=0):
    """Run the base with `selection` ({knob: value}) applied; return metrics.

    One sim per call: analyze_pipeline_bottleneck already returns the measured
    drain, and total area is static (sum of module areas, no run needed).
    Returns (drain_cycles, area_um2, bottleneck_module, total_energy_pj|None).
    """
    from npu_sim.evaluation import analyze_pipeline_bottleneck, elaborate
    from npu_sim.mapping import RuleBasedMapper

    mod_overrides: dict = {}
    for knob, value in selection.items():
        module_id, config_key = knob.split(".", 1)
        mod_overrides.setdefault(module_id, {"config": {}})["config"][config_key] = value

    override = {
        "schema_version": "1.0",
        "name": "optimize-trial",
        "base": base_abs,
        "overrides": {"modules": mod_overrides},
    }
    with tempfile.TemporaryDirectory() as d:
        vpath = Path(d) / "trial.yaml"
        vpath.write_text(yaml.safe_dump(override), encoding="utf-8")
        arch = elaborate(str(vpath))
        bn = analyze_pipeline_bottleneck(arch, max_cycles=max_cycles)
        area = sum(m.total_area_um2() for m in arch.modules.values())
        energy_pj = None
        if ops is not None:
            power = sum(m.static_power_uw() for m in arch.modules.values())
            dynamic = RuleBasedMapper(strict=False).map(ops, arch).total_dynamic_pj
            energy_pj = dynamic + power * (bn.measured_drain_cycles * period_ps) * 1e-6
    return bn.measured_drain_cycles, area, bn.bottleneck_module, energy_pj


def _objective_metric(objective: str, drain: int, energy_pj) -> float:
    """Scalar to MINIMIZE for the chosen objective (lower = better)."""
    if objective == "drain":
        return float(drain)
    if energy_pj is None:
        raise ValueError(
            f"objective '{objective}' needs energy, but the base carries no ops "
            "trace (use a TraceProducer chip, or objective='drain')."
        )
    if objective == "energy":
        return float(energy_pj)
    if objective == "edp":                       # energy-delay product
        return float(energy_pj) * float(drain)
    raise ValueError(f"unknown objective {objective!r} (drain | energy | edp)")


def optimize_bottleneck(
    base_path: str,
    knobs: dict,
    max_cycles: int = 100_000,
    max_rounds: int = 20,
    objective: str = "drain",
) -> OptimizeReport:
    """Greedily widen the bottleneck stage until the objective stops improving.

    ``knobs`` maps ``"<module_id>.<config_key>"`` → ascending list of candidate
    values (cheap/narrow first). The search starts at each knob's first value.
    ``objective`` selects what a move must improve: ``drain`` (latency),
    ``energy`` (total pJ), or ``edp`` (energy-delay product). It stays a greedy
    bottleneck-*widening* search — it never narrows an over-provisioned stage —
    so for energy/EDP it finds the best config reachable by widening, not the
    global optimum.
    """
    from npu_sim.evaluation import elaborate
    from npu_sim.evaluation.sweep import _try_load_ops

    base_abs = str(Path(base_path).resolve())
    base_arch = elaborate(base_abs)
    base_name = base_arch.name
    period_ps = base_arch.clocks[next(iter(base_arch.clocks))].period_ps
    ops = _try_load_ops(base_abs)   # None if the base carries no ops trace

    # Start at the first (baseline) value of every knob.
    idx = {k: 0 for k in knobs}
    selection = {k: knobs[k][0] for k in knobs}
    drain, area, bn, energy = _measure(base_abs, selection, max_cycles, ops, period_ps)
    metric = _objective_metric(objective, drain, energy)
    initial_drain = drain
    initial_selection = dict(selection)

    steps: list[OptimizeStep] = []
    stop_reason = "max rounds reached"

    for r in range(max_rounds):
        # Knobs that widen the current bottleneck module and have headroom.
        candidates = [
            k for k in sorted(knobs)
            if k.split(".", 1)[0] == bn and idx[k] < len(knobs[k]) - 1
        ]
        if not candidates:
            stop_reason = (
                f"bottleneck '{bn}' has no widenable knob left — converged"
            )
            break

        knob = candidates[0]
        from_v = knobs[knob][idx[knob]]
        to_v = knobs[knob][idx[knob] + 1]
        trial = dict(selection)
        trial[knob] = to_v
        t_drain, t_area, t_bn, t_energy = _measure(base_abs, trial, max_cycles, ops, period_ps)
        t_metric = _objective_metric(objective, t_drain, t_energy)

        if t_metric < metric:
            idx[knob] += 1
            selection = trial
            drain, area, bn, energy, metric = t_drain, t_area, t_bn, t_energy, t_metric
            steps.append(OptimizeStep(
                round_index=r, knob=knob, from_value=from_v, to_value=to_v,
                drain_cycles=t_drain, bottleneck_module=t_bn,
                total_area_um2=t_area, accepted=True, total_energy_pj=t_energy,
            ))
        else:
            steps.append(OptimizeStep(
                round_index=r, knob=knob, from_value=from_v, to_value=to_v,
                drain_cycles=t_drain, bottleneck_module=t_bn,
                total_area_um2=t_area, accepted=False, total_energy_pj=t_energy,
            ))
            stop_reason = (
                f"widening {knob} {from_v}→{to_v} did not improve {objective} "
                f"({metric:,.0f}→{t_metric:,.0f}) — diminishing returns"
            )
            break

    lines = [
        f"Greedy bottleneck optimization of `{base_name}` (objective: {objective}):",
        f"  initial: {initial_drain:,} cyc  {initial_selection}",
    ]
    for s in steps:
        tag = "✓" if s.accepted else "✗ (stop)"
        e = f", {s.total_energy_pj/1000:,.1f} nJ" if s.total_energy_pj is not None else ""
        lines.append(
            f"  round {s.round_index}: {s.knob} {s.from_value}→{s.to_value} "
            f"⇒ {s.drain_cycles:,} cyc{e}, bottleneck {s.bottleneck_module} {tag}"
        )
    imp = (initial_drain - drain) / initial_drain * 100 if initial_drain else 0.0
    lines.append(f"  final:   {drain:,} cyc  {selection}  ({imp:+.0f}% drain vs initial)")
    lines.append(f"  stop:    {stop_reason}")

    return OptimizeReport(
        base_name=base_name,
        knobs=tuple(sorted(knobs)),
        initial_drain_cycles=initial_drain,
        final_drain_cycles=drain,
        initial_selection=initial_selection,
        final_selection=dict(selection),
        steps=tuple(steps),
        stop_reason=stop_reason,
        objective=objective,
        summary_text="\n".join(lines),
    )
