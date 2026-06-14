"""精度不归一 use case — YAML+仿真驱动评估。

Drives:
  baseline = usecase_precision_int8_only.yaml  (MAC: INT8 only)
  variant  = usecase_precision_mixed.yaml      (MAC: INT8 + BFP16 + FP16)

Same MAC instance, three precision capabilities enabled in the variant
via config. The simulator picks up the area cost of the extra precision
lanes; drain_time is unchanged when the workload is INT8-only — proving
that "支持多精度" carries silicon cost even when not exercised.
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
    base = elaborate_and_run(
        str(FIXTURES / "usecase_precision_int8_only.yaml"), max_cycles=2000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_precision_mixed.yaml"), max_cycles=2000
    )
    return compare(base, var)


class TestPrecisionAreaCost:
    """Mixed precision adds silicon area without changing INT8-workload latency."""

    def test_mixed_precision_costs_area(self, report):
        assert report.area_delta_um2 > 0, (
            f"BFP16/FP16 capabilities should add area, "
            f"got Δ={report.area_delta_um2:+.1f} μm²"
        )

    def test_area_cost_at_least_25k_um2(self, report):
        """SPEC-005 MAC capabilities: bfp16=15k + fp16=18k = 33k μm²."""
        assert report.area_delta_um2 >= 25_000


class TestPrecisionLatencyOnInt8Workload:
    """INT8 workload latency unchanged by extra precision support."""

    def test_drain_time_unchanged(self, report):
        assert report.drain_time_delta_ps == 0, (
            f"INT8 workload should not slow down when BFP16/FP16 are added; "
            f"Δ={report.drain_time_delta_ps:+d} ps"
        )

    def test_both_runs_valid(self, report):
        assert report.both_valid


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
