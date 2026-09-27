"""MAC 算法激励 use case — YAML+仿真驱动评估。

Drives:
  baseline = mac_chain_smaller_array.yaml  (smaller MAC array)
  variant  = mac_chain.yaml                (32×32 MAC array)

Demonstrates how MAC array sizing changes throughput and bottleneck
attribution in the simulator. Pairs with test_agu_stimulus.py to cover
the user's "MAC/DSB/AGU 的算法激励" item.
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
        str(FIXTURES / "mac_chain_smaller_array.yaml"), max_cycles=2000
    )
    var = elaborate_and_run(
        str(FIXTURES / "mac_chain.yaml"), max_cycles=2000
    )
    return compare(base, var)


class TestMACArrayStimulus:
    """Larger MAC array → faster drain, MAC stops being the bottleneck."""

    def test_larger_array_reduces_drain_time(self, report):
        assert report.drain_time_delta_ps < 0, (
            f"Larger MAC array should be faster, "
            f"got Δ={report.drain_time_delta_ps:+d} ps"
        )

    def test_drain_time_speedup_at_least_20pct(self, report):
        pct = -report.drain_time_delta_pct
        assert pct >= 20.0, (
            f"Larger array speedup {pct:.1f}% below 20% threshold"
        )

    def test_mac_bottleneck_shifts(self, report):
        """SPEC-002 §3.3: bottleneck attribution should detect MAC is no
        longer the limiting stage when the array is sized up."""
        assert report.baseline.bottleneck_module == "mac", (
            f"Baseline bottleneck should be MAC, got {report.baseline.bottleneck_module!r}"
        )
        assert report.variant.bottleneck_module != "mac", (
            f"Variant bottleneck should leave MAC, "
            f"got {report.variant.bottleneck_module!r}"
        )

    def test_both_runs_valid(self, report):
        assert report.both_valid


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
