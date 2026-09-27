"""End-to-end runtime test for the DAGC module (first real module).

Producer -> DAGC -> Consumer over real TlmConnections. Validates that DAGC
participates correctly in the Phase 2 runtime (SPEC-001 §3, SPEC-002 §3):

  - the happy-path chain drains all tokens with no deadlock (INV-3) and DAGC
    unpacks exactly the tokens the producer emitted;
  - a slow downstream consumer makes DAGC's output port stall, and the
    backpressure is attributed to the consumer (SPEC-002 §3.5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate_and_run
import npu_sim.modules  # noqa: F401  registers Producer / DAGC / Consumer


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture
def chain_result():
    return elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=500)


@pytest.fixture
def slow_result():
    return elaborate_and_run(str(FIXTURES / "dagc_slow_consumer.yaml"), max_cycles=2000)


class TestDAGCHappyPath:

    def test_chain_is_valid(self, chain_result):
        assert chain_result.invariant_report.overall_valid, \
            chain_result.invariant_report.summary_text

    def test_all_tokens_flow_through_dagc(self, chain_result):
        # Two connections; each carries all 16 tokens end to end.
        assert chain_result.tokens_delivered == {
            "prod.out→dagc.in_packed": 16,
            "dagc.out_unpacked→cons.in": 16,
        }
        assert all(v == 0 for v in chain_result.tokens_in_flight.values())

    def test_happy_path_has_no_bottleneck(self, chain_result):
        # DAGC lanes are fast enough that nothing stalls.
        assert chain_result.total_stall_ps == 0
        assert chain_result.bottleneck_module is None

    def test_area_includes_dagc_capabilities(self, chain_result):
        # DAGC dominates area; sanity-check it is counted (all 4 caps active).
        assert chain_result.total_area_um2 >= 3500.0 + 6200.0 + 4100.0 + 2300.0


class TestDAGCBackpressure:

    def test_slow_consumer_chain_still_valid(self, slow_result):
        assert slow_result.invariant_report.overall_valid, \
            slow_result.invariant_report.summary_text

    def test_dagc_output_stalls_on_slow_consumer(self, slow_result):
        assert slow_result.per_module_stall_ps.get("dagc", 0) > 0

    def test_bottleneck_traces_to_consumer(self, slow_result):
        assert slow_result.bottleneck_module == "cons"

    def test_all_tokens_delivered_despite_backpressure(self, slow_result):
        assert slow_result.tokens_delivered["dagc.out_unpacked→cons.in"] == 16
