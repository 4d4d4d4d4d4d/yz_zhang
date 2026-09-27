"""SPEC-007 §7.3 — MAC/DSB/AGU 算法激励,通过仿真驱动评估。

Drives:
  baseline = usecase_agu_shallow.yaml  (pipeline_depth=1, no fill stall)
  variant  = usecase_agu_deep.yaml     (pipeline_depth=8, +7 fill cycles)

The fill stall is realized in the simulator: variant.drain_time should be
exactly +7 cycles vs baseline for the first token, amortizing to 0 over
many tokens.
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
    base = elaborate_and_run(str(FIXTURES / "usecase_agu_shallow.yaml"), max_cycles=2000)
    var = elaborate_and_run(str(FIXTURES / "usecase_agu_deep.yaml"), max_cycles=2000)
    return compare(base, var)


class TestAGUPipelineDepthImpact:
    """§7.3.1: fill stall = pipeline_depth - 1 (one-time)."""

    def test_deep_pipeline_adds_fill_stall(self, report):
        delta_ps = report.drain_time_delta_ps
        # depth=8 vs depth=1 → +7 cycles × 1000 ps/cycle = +7000 ps.
        assert delta_ps == 7000, (
            f"AGU depth=8 vs depth=1 should add exactly +7000 ps fill, "
            f"got {delta_ps:+d} ps"
        )

    def test_steady_state_throughput_unchanged(self, report):
        """§7.3.1: pipeline_depth only affects fill, not steady-state rate.
        Per-token cycles after fill should match."""
        # Both runs process 4 tokens × 64 addrs/token = 256 effective work
        # cycles. Variant pays +7 fill once. Δ/total should be < 3%.
        delta_pct = abs(report.drain_time_delta_pct)
        assert delta_pct <= 3.0, (
            f"§7.3.1: throughput should be steady; Δ {delta_pct:.1f}% > 3%"
        )

    def test_area_unchanged_by_depth(self, report):
        """v1.0 model: pipeline_depth doesn't change declared capability area."""
        assert report.area_delta_um2 == 0.0


class TestAGUMACDSBStimulus:
    """§7.3.2 stimulus: the depth/throughput tradeoff is observable."""

    def test_both_runs_valid(self, report):
        assert report.both_valid

    def test_tokens_delivered_match(self, report):
        """Throughput parity: same number of tokens flow through."""
        for key in report.baseline.tokens_delivered:
            assert report.baseline.tokens_delivered[key] == \
                   report.variant.tokens_delivered.get(key, 0), (
                f"Token count mismatch on {key}"
            )


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
