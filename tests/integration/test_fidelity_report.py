"""Chip PPA-fidelity report — how much of a chip is physically grounded.

Directly answers "is this real?" for any config: classifies each module's
area model (physical / hybrid / placeholder) from its own provenance note and
reports the grounded fraction. A meta-report over estimate_area().notes, so it
tracks migrations automatically.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.evaluation import chip_fidelity, elaborate
from npu_sim.evaluation.fidelity import _classify
from npu_sim.reporting import render_fidelity_report
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
FULL = "usecase_npu_v4_full_stack.yaml"
CHIP = "usecase_chip_trace_driven.yaml"


class TestClassify:
    def test_physical_note(self):
        assert _classify("SPEC-013 physical @45nm SRAM macro") == "physical"

    def test_placeholder_note(self):
        assert _classify("SPEC-007 §2.4.1 [calibration knob]") == "placeholder"

    def test_hybrid_note(self):
        assert _classify("SPEC-007 FSM [calibration knob] + SPEC-013 physical") == "hybrid"

    def test_empty_note_is_placeholder(self):
        assert _classify("") == "placeholder"


class TestChipFidelity:
    @pytest.fixture(scope="class")
    def report(self):
        return chip_fidelity(elaborate(str(FIXTURES / FULL)))

    def test_grounded_modules_classified_physical(self, report):
        status = {m.module_id: m.status for m in report.modules}
        for grounded in ("mac", "l2", "tlu", "dsb", "avp"):
            assert status[grounded] == "physical", grounded

    def test_control_modules_are_placeholder(self, report):
        status = {m.module_id: m.status for m in report.modules}
        assert status["mcu"] == "placeholder"

    def test_total_area_is_sum_of_modules(self, report):
        assert report.total_area_um2 == pytest.approx(
            sum(m.area_um2 for m in report.modules)
        )

    def test_grounded_pct_dominant_on_a_realistic_chip(self, report):
        # the large-area blocks (compute + storage) are grounded → majority
        assert report.grounded_pct > 80.0

    def test_modules_sorted_by_area_desc(self, report):
        areas = [m.area_um2 for m in report.modules]
        assert areas == sorted(areas, reverse=True)


class TestTraceChipFullyGrounded:
    def test_datapath_chip_is_100pct_grounded(self):
        # trace-driven datapath: trace_src(virtual) + DAGC/DSB/MAC/VAU/AVP +
        # sink — all grounded or zero-area, so ~100%.
        report = chip_fidelity(elaborate(str(FIXTURES / CHIP)))
        assert report.grounded_pct > 99.0


class TestRenderAndCLI:
    def test_render_has_breakdown(self):
        report = chip_fidelity(elaborate(str(FIXTURES / FULL)))
        md = render_fidelity_report(report, arch_name="chip")
        assert "Chip PPA fidelity" in md
        assert "physical" in md and "placeholder" in md
        assert "Per-module" in md

    def test_cli_fidelity(self):
        buf = io.StringIO()
        rc = cli_main(["fidelity", str(FIXTURES / FULL)], out=buf)
        assert rc == 0
        s = buf.getvalue()
        assert "area on grounded models" in s
        assert "`mac`" in s
