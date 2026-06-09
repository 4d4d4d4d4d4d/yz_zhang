"""SPEC-007 §2.5 — OGU 节省 MCU 负载,通过仿真驱动评估。

Drives:
  baseline = usecase_mcu_baseline.yaml          (MCU alone, no OGU)
  variant  = usecase_mcu_with_ogu.yaml          (MCU + OGU peer)

The evaluation runs the full simulator on each YAML; compare() surfaces
drain_time / area / stall deltas. Test asserts §2.5 formal criteria.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def report():
    base = elaborate_and_run(str(FIXTURES / "usecase_mcu_baseline.yaml"), max_cycles=5000)
    var = elaborate_and_run(str(FIXTURES / "usecase_mcu_with_ogu.yaml"), max_cycles=5000)
    return compare(base, var)


class TestOGUSpeedup:
    """§3.3.2: T_mcu_baseline / T_mcu_with_ogu ≥ 2× (target)."""

    def test_drain_time_speedup_meets_2x_target(self, report):
        speedup = report.baseline.drain_time_ps / report.variant.drain_time_ps
        assert speedup >= 2.0, (
            f"§3.3.2 OGU speedup {speedup:.2f}× below 2× target "
            f"(baseline {report.baseline.drain_time_ps} ps, "
            f"variant {report.variant.drain_time_ps} ps)"
        )

    def test_drain_time_speedup_matches_offload_ratio(self, report):
        """Spec ratio 260/60 ≈ 4.33× — actual sim should be close once
        Producer/Consumer overhead is accounted for."""
        speedup = report.baseline.drain_time_ps / report.variant.drain_time_ps
        assert speedup >= 3.5, (
            f"OGU speedup {speedup:.2f}× far below 4.33× spec target"
        )


class TestSaveNMcuCriteria:
    """§2.5.2: variant ≤ baseline × 1.05 AND fewer MCUs."""

    def test_variant_uses_fewer_mcus_with_same_throughput(self, report):
        """With OGU, 1 MCU achieves throughput of 2+ baseline MCUs."""
        # Baseline has 1 MCU; variant has 1 MCU + 1 OGU.
        # Speedup ≥ 2× means variant 1 MCU replaces baseline 2 MCUs.
        speedup = report.baseline.drain_time_ps / report.variant.drain_time_ps
        replaceable_mcus = int(speedup)
        assert replaceable_mcus >= 2, (
            f"§2.5.3 single-thread target: 1 MCU + 1 OGU should replace 2 "
            f"MCUs, actual speedup {speedup:.2f}× → {replaceable_mcus} MCUs"
        )

    def test_invariants_hold_for_both_runs(self, report):
        assert report.both_valid


class TestOGUAreaImpact:
    """§3.4.1: OGU is small enough that variant area ≤ baseline area."""

    def test_variant_total_area_no_worse_than_baseline(self, report):
        # In our SPEC-007 model, OGU offload disables MCU fallback caps so
        # the variant is actually smaller than the baseline.
        assert report.area_delta_um2 <= 0, (
            f"With OGU offload, MCU fallback caps deactivate. Expected "
            f"area_delta ≤ 0, got {report.area_delta_um2:+.1f} μm²"
        )

    def test_ogu_smaller_than_replaced_mcu_work(self, report):
        """§3.4.1 design intent: OGU area < area of work it replaces."""
        # Baseline area = full MCU. Variant area = stripped MCU + OGU.
        # If OGU < (full MCU - stripped MCU), variant ≤ baseline.
        assert report.variant.total_area_um2 < report.baseline.total_area_um2


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
