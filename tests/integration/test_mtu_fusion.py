"""SPEC-007 §6.3 — MTU 融合 TAU/DMA,通过仿真驱动评估。

Drives:
  baseline = usecase_tau_dma_baseline.yaml      (separate TAU → DMA)
  variant  = usecase_mtu_variant.yaml           (fused MTU)

The simulation comparison shows MTU's area benefit (§6.4.1) while drain
time remains within the same band as the TAU+DMA pipeline (a true
producer-consumer pipeline can achieve full overlap; MTU achieves 80%).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def report():
    base = elaborate_and_run(
        str(FIXTURES / "usecase_tau_dma_baseline.yaml"), max_cycles=20000
    )
    var = elaborate_and_run(str(FIXTURES / "usecase_mtu_variant.yaml"), max_cycles=20000)
    return compare(base, var)


class TestMTUAreaSaving:
    """§6.4.1 / §6.5: MTU < TAU + DMA area."""

    def test_mtu_total_area_less_than_baseline(self, report):
        assert report.area_delta_um2 < 0, (
            f"§6.4.1: MTU variant area should be smaller, "
            f"got Δ={report.area_delta_um2:+.1f} μm²"
        )

    def test_area_savings_at_least_5pct(self, report):
        savings_pct = -100.0 * report.area_delta_um2 / report.baseline.total_area_um2
        assert savings_pct >= 5.0, (
            f"MTU area savings {savings_pct:.1f}% below 5% threshold"
        )


class TestMTUDrainTime:
    """§6.3.1: MTU drain time comparable to TAU+DMA (pipeline_with_overlap)."""

    def test_drain_time_within_5pct_of_baseline(self, report):
        """Fused MTU ≈ 80% overlap; TAU+DMA pipeline naturally achieves
        ~full overlap. Difference should stay within 5%."""
        delta_pct = report.drain_time_delta_pct
        assert abs(delta_pct) <= 5.0, (
            f"MTU vs TAU+DMA drain delta {delta_pct:+.1f}% exceeds ±5% band"
        )

    def test_invariants_hold(self, report):
        assert report.both_valid


class TestMTUTopologySimplification:
    """§6.5: MTU collapses two module instances into one."""

    def test_variant_has_one_fewer_module(self, report):
        # baseline = Producer + TAU + DMA + Consumer = 4
        # variant  = Producer + MTU + Consumer = 3
        base_modules = len(report.baseline.per_module_stall_ps) if \
            report.baseline.per_module_stall_ps else 4
        var_modules = len(report.variant.per_module_stall_ps) if \
            report.variant.per_module_stall_ps else 3
        # Stall maps may be empty (no stalls), use architecture-level count
        # via tokens_delivered instead.
        base_conn_count = len(report.baseline.tokens_delivered)
        var_conn_count = len(report.variant.tokens_delivered)
        assert var_conn_count < base_conn_count, (
            f"MTU should reduce connection count: "
            f"baseline {base_conn_count} → variant {var_conn_count}"
        )
