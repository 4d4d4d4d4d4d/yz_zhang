"""End-to-end Use Case test: baseline vs slow-consumer variant.

Demonstrates the SPEC-003 §7 R7 evaluation pattern using only the v1.0
contract surface — no probe-module-specific assertions beyond expected
tokens delivered. Validates that:

  - Both runs pass invariant checks (no false-positive INV-3 from idle
    consumers; cleanly drains all tokens).
  - The variant has more cycles and more stall time than the baseline.
  - The variant's bottleneck is the consumer; the baseline has no
    bottleneck because no stalls happened.
  - The comparison summary identifies the change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401  registers Producer / Consumer


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture
def baseline_result():
    return elaborate_and_run(
        str(FIXTURES / "usecase_baseline.yaml"),
        max_cycles=500,
    )


@pytest.fixture
def variant_result():
    return elaborate_and_run(
        str(FIXTURES / "usecase_variant_slow_cons.yaml"),
        max_cycles=500,
    )


class TestUseCaseRunner:

    def test_baseline_is_valid(self, baseline_result):
        assert baseline_result.invariant_report.overall_valid, \
            baseline_result.invariant_report.summary_text

    def test_baseline_delivers_all_tokens(self, baseline_result):
        # Single connection in this fixture.
        assert sum(baseline_result.tokens_delivered.values()) == 16
        assert all(v == 0 for v in baseline_result.tokens_in_flight.values())

    def test_baseline_has_no_stalls(self, baseline_result):
        assert baseline_result.total_stall_ps == 0
        assert baseline_result.bottleneck_module is None
        assert baseline_result.per_module_stall_ps == {}

    def test_variant_is_valid(self, variant_result):
        assert variant_result.invariant_report.overall_valid, \
            variant_result.invariant_report.summary_text

    def test_variant_has_stalls_at_consumer_bottleneck(self, variant_result):
        assert variant_result.total_stall_ps > 0
        assert variant_result.bottleneck_module == "cons"

    def test_variant_delivers_all_tokens_despite_slowdown(self, variant_result):
        assert sum(variant_result.tokens_delivered.values()) == 16


class TestUseCaseComparison:

    def test_variant_is_slower_than_baseline(self, baseline_result, variant_result):
        report = compare(baseline_result, variant_result)
        assert report.cycle_delta > 0
        assert report.cycle_delta_pct > 0
        assert report.stall_delta_ps > 0
        assert report.both_valid

    def test_bottleneck_changed_in_report(self, baseline_result, variant_result):
        report = compare(baseline_result, variant_result)
        assert report.bottleneck_changed
        assert report.baseline_bottleneck is None
        assert report.variant_bottleneck == "cons"

    def test_summary_mentions_key_deltas(self, baseline_result, variant_result):
        report = compare(baseline_result, variant_result)
        text = report.summary_text
        assert "VALID" in text
        assert "cons" in text
        assert "CHANGED" in text  # bottleneck flipped from None to cons
        assert "cycles_run" in text
        assert "bottleneck" in text

    def test_per_module_stall_delta_aligns(self, baseline_result, variant_result):
        report = compare(baseline_result, variant_result)
        # Producer stall jumped from 0 to a positive value.
        assert report.per_module_stall_delta_ps.get("prod", 0) > 0

    def test_area_unchanged_for_config_only_variant(
        self, baseline_result, variant_result
    ):
        # The variant only adjusts a rate scalar, not capability flags, so
        # area / static power should be identical.
        report = compare(baseline_result, variant_result)
        assert report.area_delta_um2 == 0.0
        assert report.static_power_delta_uw == 0.0
