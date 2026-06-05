"""SPEC-003 v1.1 §2.1 — 提频 use case.

Baseline runs at 1 GHz (1000 ps period); variant at 2 GHz (500 ps period).
Same data path, same cycle counts; drain_time_ps should approximately
halve. This proves that the existing clock_domains infrastructure (SPEC-003
§3.7, already in v1.0) covers the user's "提频" evaluation — the v1.1
clock_domain amendment is a labelling/per-module-domain refinement, not a
new capability.
"""

from __future__ import annotations

from pathlib import Path

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestFrequencyScaling:
    def test_drain_time_halves_at_2x_clock(self):
        baseline = elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=400)
        variant = elaborate_and_run(str(FIXTURES / "usecase_high_freq.yaml"), max_cycles=400)

        # Same cycles_run (logical scheduling identical), but sim_time_ps
        # and drain_time_ps should be ~half because period_ps shrank 2×.
        assert variant.cycles_run == baseline.cycles_run, (
            f"Cycle counts should match (same workload, same logic): "
            f"baseline={baseline.cycles_run}, variant={variant.cycles_run}"
        )
        assert variant.drain_time_ps == baseline.drain_time_ps // 2 or \
               abs(variant.drain_time_ps * 2 - baseline.drain_time_ps) <= 2, (
            f"drain_time should halve at 2× freq: "
            f"baseline={baseline.drain_time_ps} ps, "
            f"variant={variant.drain_time_ps} ps"
        )

    def test_compare_report_picks_up_drain_time_delta(self):
        baseline = elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=400)
        variant = elaborate_and_run(str(FIXTURES / "usecase_high_freq.yaml"), max_cycles=400)
        report = compare(baseline, variant)
        # Negative delta: variant is faster.
        assert report.drain_time_delta_ps < 0
        # Roughly -50%.
        assert -55.0 <= report.drain_time_delta_pct <= -45.0, (
            f"drain_time_delta_pct = {report.drain_time_delta_pct:.1f}%, "
            f"expected ≈ -50%"
        )
        # Area unchanged — freq scaling is timing-only.
        assert abs(report.area_delta_um2) < 1e-3
