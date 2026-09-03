"""End-to-end runtime test for the DSB module. SPEC-005 §6.3, SPEC-002 §6.

Producer -> DSB -> Consumer over real TlmConnections: the happy path drains all
tokens with no deadlock (INV-3); a slow consumer makes DSB's output stall, and
the backpressure is attributed to the consumer (SPEC-002 §3.5).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate_and_run
import npu_sim.modules  # noqa: F401  registers Producer / DSB / Consumer


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture
def chain_result():
    return elaborate_and_run(str(FIXTURES / "dsb_chain.yaml"), max_cycles=500)


@pytest.fixture
def slow_result():
    return elaborate_and_run(str(FIXTURES / "dsb_slow_consumer.yaml"), max_cycles=2000)


class TestDSBHappyPath:

    def test_chain_is_valid(self, chain_result):
        assert chain_result.invariant_report.overall_valid, \
            chain_result.invariant_report.summary_text

    def test_all_tokens_flow_through_dsb(self, chain_result):
        assert chain_result.tokens_delivered == {
            "prod.out→dsb.in_data": 16,
            "dsb.out_data→cons.in": 16,
        }
        assert all(v == 0 for v in chain_result.tokens_in_flight.values())

    def test_happy_path_has_no_bottleneck(self, chain_result):
        assert chain_result.total_stall_ps == 0
        assert chain_result.bottleneck_module is None


class TestDSBBackpressure:

    def test_slow_consumer_chain_still_valid(self, slow_result):
        assert slow_result.invariant_report.overall_valid, \
            slow_result.invariant_report.summary_text

    def test_dsb_output_stalls_on_slow_consumer(self, slow_result):
        assert slow_result.per_module_stall_ps.get("dsb", 0) > 0

    def test_bottleneck_traces_to_consumer(self, slow_result):
        assert slow_result.bottleneck_module == "cons"

    def test_all_tokens_delivered_despite_backpressure(self, slow_result):
        assert slow_result.tokens_delivered["dsb.out_data→cons.in"] == 16
