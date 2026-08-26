"""Design-space sweep — the cost of a hardware change, YAML-driven.

The recurring evaluation question ("评估硬件变化的代价"): given a base chip,
what does changing one knob buy? The `bottleneck` tool names the limiting
stage; this sweeps that stage's config over a range and reports the PPA
response, so "widen avp" becomes a number: drain −42%, area +X%.

It also surfaces the classic diminishing-returns law directly — as the swept
stage speeds up, the bottleneck eventually shifts to another module and
further widening stops helping. The report flags the shift.

Each sweep point is a real simulation of a real override: for every value a
tiny override DSL is written (``base:`` the untouched base file, ``overrides``
setting one ``modules.<id>.config.<key>``), elaborated and run through the
same path as any hand-written variant. Nothing is constructed in Python and
no estimate_* is called — the sweep stays inside the YAML-driven contract:
change a config file, the sim produces the result.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import yaml


@dataclass(frozen=True)
class SweepPoint:
    """One value of the swept parameter and its measured PPA response."""

    value: object
    drain_cycles: int
    total_area_um2: float
    static_power_uw: float
    bottleneck_module: Optional[str]
    bottleneck_ii: float
    total_energy_pj: Optional[float] = None   # None if base carries no ops trace


@dataclass(frozen=True)
class SweepReport:
    """A parameter sweep over one config field of one module."""

    base_name: str
    param_path: str                     # "<module_id>.<config_key>"
    points: tuple[SweepPoint, ...]
    baseline_drain_cycles: int          # first point's drain (reference)
    best_value: object                  # value giving the lowest drain
    bottleneck_shifted: bool            # did the bottleneck move during the sweep?
    summary_text: str = ""


def sweep_config(
    base_path: str,
    module_id: str,
    config_key: str,
    values: Sequence[object],
    max_cycles: int = 100_000,
) -> SweepReport:
    """Sweep ``modules.<module_id>.config.<config_key>`` over ``values``.

    Each value is materialised as an override DSL on top of ``base_path`` and
    run; the point records drain (cycles), area, static power and the measured
    pipeline bottleneck. Returns a :class:`SweepReport` ranking the values and
    flagging any bottleneck shift.
    """
    # Local import keeps evaluation.__init__ import order simple.
    from npu_sim.evaluation import analyze_pipeline_bottleneck, elaborate
    from npu_sim.mapping import RuleBasedMapper

    base_abs = str(Path(base_path).resolve())
    base_arch = elaborate(base_abs)
    base_name = base_arch.name  # the untouched base's identity
    period_ps = base_arch.clocks[next(iter(base_arch.clocks))].period_ps
    ops = _try_load_ops(base_abs)   # None if the base carries no ops trace
    points: list[SweepPoint] = []

    for value in values:
        override = {
            "schema_version": "1.0",
            "name": f"sweep {module_id}.{config_key}={value}",
            "base": base_abs,
            "overrides": {
                "modules": {module_id: {"config": {config_key: value}}}
            },
        }
        with tempfile.TemporaryDirectory() as d:
            vpath = Path(d) / "variant.yaml"
            vpath.write_text(yaml.safe_dump(override), encoding="utf-8")
            arch = elaborate(str(vpath))
            # One sim: analyze returns the measured drain; area/power are static.
            bn = analyze_pipeline_bottleneck(arch, max_cycles=max_cycles)
            area = sum(m.total_area_um2() for m in arch.modules.values())
            power = sum(m.static_power_uw() for m in arch.modules.values())
            energy_pj = None
            if ops is not None:
                # dynamic (per-op, Horowitz) + static (power × runtime); no
                # extra sim — reuses the drain already measured.
                dynamic = RuleBasedMapper(strict=False).map(ops, arch).total_dynamic_pj
                static = power * (bn.measured_drain_cycles * period_ps) * 1e-6
                energy_pj = dynamic + static

        points.append(SweepPoint(
            value=value,
            drain_cycles=bn.measured_drain_cycles,
            total_area_um2=area,
            static_power_uw=power,
            bottleneck_module=bn.bottleneck_module,
            bottleneck_ii=bn.bottleneck_ii,
            total_energy_pj=energy_pj,
        ))

    baseline = points[0].drain_cycles if points else 0
    best = min(points, key=lambda p: p.drain_cycles).value if points else None
    bottlenecks = {p.bottleneck_module for p in points}
    shifted = len(bottlenecks) > 1

    lines = [f"Sweep {module_id}.{config_key} over {list(values)}:"]
    for p in points:
        dpct = (
            (p.drain_cycles - baseline) / baseline * 100 if baseline else 0.0
        )
        lines.append(
            f"  {config_key}={p.value}: drain {p.drain_cycles:,} cyc "
            f"({dpct:+.0f}%), area {p.total_area_um2:,.0f} um², "
            f"bottleneck {p.bottleneck_module}@II={p.bottleneck_ii:.0f}"
        )
    lines.append(f"  best drain at {config_key}={best}")
    if shifted:
        lines.append(
            "  ⚠ bottleneck shifted during the sweep — further widening the "
            "original stage yields diminishing returns."
        )
    return SweepReport(
        base_name=base_name,
        param_path=f"{module_id}.{config_key}",
        points=tuple(points),
        baseline_drain_cycles=baseline,
        best_value=best,
        bottleneck_shifted=shifted,
        summary_text="\n".join(lines),
    )


def _try_load_ops(base_path: str):
    """Load the workload ops from the base (a TraceProducer fixture), or None
    if the base carries no trace — energy is then simply not reported."""
    from npu_sim.evaluation.trace_ops import load_ops
    try:
        ops = load_ops(base_path)
        return ops or None
    except (ValueError, FileNotFoundError, KeyError):
        return None
