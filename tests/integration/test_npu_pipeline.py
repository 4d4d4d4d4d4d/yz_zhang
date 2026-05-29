"""Full Phase 2 datapath integration. SPEC-005 §0 composition, SPEC-002 §6/§7.

Producer -> DAGC -> DSB -> MAC -> VAU -> AVP -> Consumer over real
TlmConnections. Proves the five real modules compose into a working NPU
pipeline (no deadlock, all tokens drain end to end) and that the evaluation
comparator (SPEC-003 §7 R7) detects a throughput regression when one stage is
narrowed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401  registers all module types


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"

# Every connection in the datapath, in flow order.
_PIPELINE_CONNECTIONS = [
    "prod.out→dagc.in_packed",
    "dagc.out_unpacked→dsb.in_data",
    "dsb.out_data→mac.in_act",
    "mac.out_psum→vau.in_a",
    "vau.out→avp.in_data",
    "avp.out_data→cons.in",
]


# Equal budget for both runs so stall time is an apples-to-apples regression
# signal. cycles_run is NOT comparable here: module behaviors loop forever, so
# the scheduler always runs to max_cycles (see docs/specs/README.md finding).
_MAX_CYCLES = 8000


@pytest.fixture
def baseline():
    return elaborate_and_run(str(FIXTURES / "npu_pipeline.yaml"), max_cycles=_MAX_CYCLES)


@pytest.fixture
def narrow_avp():
    return elaborate_and_run(
        str(FIXTURES / "npu_pipeline_narrow_avp.yaml"), max_cycles=_MAX_CYCLES
    )


class TestPipelineComposition:

    def test_pipeline_is_valid(self, baseline):
        assert baseline.invariant_report.overall_valid, \
            baseline.invariant_report.summary_text

    def test_all_stages_carry_every_token(self, baseline):
        # 16 tokens must traverse all six connections end to end.
        for conn in _PIPELINE_CONNECTIONS:
            assert baseline.tokens_delivered[conn] == 16, conn

    def test_no_tokens_left_in_flight(self, baseline):
        assert all(v == 0 for v in baseline.tokens_in_flight.values())

    def test_area_aggregates_all_modules(self, baseline):
        # DAGC + DSB + MAC + VAU + AVP capability areas all contribute; the
        # MAC int8 array alone is 42000 um², so the total must exceed it.
        assert baseline.total_area_um2 > 42000.0


class TestPipelineRegression:
    """SPEC-003 §7 R7: compare baseline vs a narrowed-AVP variant."""

    def test_both_runs_valid(self, baseline, narrow_avp):
        report = compare(baseline, narrow_avp)
        assert report.both_valid

    def test_narrow_avp_adds_stall(self, baseline, narrow_avp):
        report = compare(baseline, narrow_avp)
        # Quartering AVP throughput makes upstream stages stall waiting on it.
        assert report.stall_delta_ps > 0

    def test_avp_remains_the_bottleneck(self, baseline, narrow_avp):
        assert baseline.bottleneck_module == "avp"
        assert narrow_avp.bottleneck_module == "avp"

    def test_variant_delivers_all_tokens_despite_regression(self, narrow_avp):
        assert narrow_avp.tokens_delivered["avp.out_data→cons.in"] == 16

    def test_summary_renders(self, baseline, narrow_avp):
        report = compare(baseline, narrow_avp)
        assert "baseline" in report.summary_text and "variant" in report.summary_text
