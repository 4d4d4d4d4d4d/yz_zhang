"""DSB / 大算子对能效 use case — YAML+仿真驱动评估。

Drives:
  baseline = usecase_dsb_small_op.yaml  (16 × 8-byte tokens)
  variant  = usecase_dsb_large_op.yaml  (4 × 1024-byte tokens)

Same DSB instance, different workload token size. The drain_time delta
quantifies how DSB's per-token cost scales with payload size; area is
identical because DSB silicon doesn't depend on the workload.
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
        str(FIXTURES / "usecase_dsb_small_op.yaml"), max_cycles=2000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_dsb_large_op.yaml"), max_cycles=2000
    )
    return compare(base, var)


class TestDSBWorkloadSensitivity:
    """Drain time should grow with per-token payload size on the DSB."""

    def test_large_op_takes_longer(self, report):
        assert report.drain_time_delta_ps > 0, (
            f"Large tokens should take longer per-token in DSB, "
            f"got Δ={report.drain_time_delta_ps:+d} ps"
        )

    def test_area_unchanged_by_workload(self, report):
        """Workload changes do not move silicon area."""
        assert report.area_delta_um2 == pytest.approx(0.0, abs=1e-3)

    def test_static_power_unchanged_by_workload(self, report):
        assert report.static_power_delta_uw == pytest.approx(0.0, abs=1e-3)

    def test_both_runs_valid(self, report):
        assert report.both_valid


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
