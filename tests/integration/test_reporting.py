"""Markdown rendering tests for SimulationResult / ComparisonReport.

Reference: implementation of the report renderers in npu_sim/reporting/.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
from npu_sim.reporting import (
    render_comparison_report,
    render_simulation_report,
)
import npu_sim.modules  # noqa: F401  register probe modules


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture
def baseline():
    return elaborate_and_run(
        str(FIXTURES / "usecase_baseline.yaml"), max_cycles=500
    )


@pytest.fixture
def variant():
    return elaborate_and_run(
        str(FIXTURES / "usecase_variant_slow_cons.yaml"), max_cycles=500
    )


class TestSimulationReport:

    def test_baseline_report_basic_structure(self, baseline):
        md = render_simulation_report(baseline)
        # Header + status + main sections.
        assert "# Simulation Report:" in md
        assert "VALID" in md
        assert "## Summary" in md
        assert "## Invariants" in md
        assert "## Token Flow" in md
        # Baseline has no stalls.
        assert "No stalls recorded" in md
        # Pasteable markdown tables.
        assert "| Metric | Value |" in md

    def test_variant_report_highlights_bottleneck(self, variant):
        md = render_simulation_report(variant)
        assert "VALID" in md
        # Variant has a real bottleneck.
        assert "**Bottleneck:**" in md
        assert "cons" in md
        # Per-module stall table present.
        assert "## Stall Analysis" in md
        assert "| Module | Stall (ps) |" in md

    def test_report_handles_invalid_runs(self):
        # Use the never-consume fixture: scheduler times out, both INV-2 and
        # INV-3 fire.
        result = elaborate_and_run(
            str(FIXTURES / "probe_never_consume.yaml"),
            max_cycles=30,
        )
        md = render_simulation_report(result)
        assert "INVALID" in md
        assert "INV-" in md  # at least one invariant id is rendered

    def test_token_flow_section_lists_connections(self, baseline):
        md = render_simulation_report(baseline)
        # The single connection's key uses our "src.port→sink.port" format.
        assert "prod.out→cons.in" in md


class TestComparisonReport:

    def test_full_comparison_structure(self, baseline, variant):
        report = compare(baseline, variant)
        md = render_comparison_report(report)
        # Header + summary + key sections.
        assert "# Comparison:" in md
        assert "✅ VALID" in md
        assert "## Summary" in md
        assert "## Bottleneck Change" in md
        assert "## Per-module Stall Delta" in md
        assert "## Invariants" in md

    def test_summary_table_columns(self, baseline, variant):
        md = render_comparison_report(compare(baseline, variant))
        assert "| Metric | Baseline | Variant | Δ |" in md
        # Cycle delta sign rendered.
        assert "+" in md  # variant has more cycles
        assert "CHANGED" in md  # bottleneck flipped

    def test_no_per_module_section_when_no_stalls(self):
        b = elaborate_and_run(
            str(FIXTURES / "usecase_baseline.yaml"), max_cycles=500
        )
        # Compare baseline against itself — no deltas at all.
        md = render_comparison_report(compare(b, b))
        # When no module has any stall in either run, the section is omitted.
        assert "## Per-module Stall Delta" not in md
        # Bottleneck not changed, callout omitted.
        assert "## Bottleneck Change" not in md
