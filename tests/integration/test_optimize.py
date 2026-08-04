"""Greedy bottleneck-chasing optimizer — automated design search.

Composes `bottleneck` + `sweep` into a loop: widen the limiting stage, watch
the bottleneck move, widen the next one, stop when widening stops paying off.
The headline run chases avp → dsb → vau and converges when it hits a stage
with no knob left.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.evaluation import optimize_bottleneck
from npu_sim.reporting import render_optimize_report
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
KNOBS = {"avp.vector_width": [16, 32, 64], "dsb.read_throughput": [8, 16]}


@pytest.fixture(scope="module")
def report():
    return optimize_bottleneck(str(FIXTURES / CHIP), KNOBS)


class TestGreedySearch:
    def test_final_drain_beats_initial(self, report):
        assert report.final_drain_cycles < report.initial_drain_cycles
        assert report.drain_improvement_pct > 0

    def test_every_accepted_step_strictly_improves(self, report):
        prev = report.initial_drain_cycles
        for s in report.steps:
            if s.accepted:
                assert s.drain_cycles < prev
                prev = s.drain_cycles

    def test_chases_bottleneck_across_modules(self, report):
        # first move targets avp (the initial bottleneck); a later move targets dsb
        touched = [s.knob.split(".")[0] for s in report.steps if s.accepted]
        assert touched[0] == "avp"
        assert "dsb" in touched

    def test_converges_on_unwidenable_stage(self, report):
        # search ends because the live bottleneck (vau) has no knob provided
        assert "converged" in report.stop_reason or "diminishing" in report.stop_reason
        assert report.final_selection["avp.vector_width"] == 64

    def test_deterministic(self, report):
        again = optimize_bottleneck(str(FIXTURES / CHIP), KNOBS)
        assert again.final_selection == report.final_selection
        assert again.final_drain_cycles == report.final_drain_cycles
        assert again.stop_reason == report.stop_reason


class TestStopConditions:
    def test_single_knob_stops_when_bottleneck_moves_off_it(self):
        # only an avp knob: once the bottleneck leaves avp, no candidate remains
        r = optimize_bottleneck(
            str(FIXTURES / CHIP), {"avp.vector_width": [16, 32, 64]}
        )
        assert r.final_selection["avp.vector_width"] in (32, 64)
        assert r.final_drain_cycles < r.initial_drain_cycles
        # bottleneck ends up off avp (moved to dsb/vau) → converged
        assert "converged" in r.stop_reason


class TestRenderAndCLI:
    def test_render_has_trace_and_final(self, report):
        md = render_optimize_report(report)
        assert "Bottleneck optimization" in md
        assert "Search trace" in md
        assert "Final design" in md

    def test_cli_optimize(self):
        buf = io.StringIO()
        rc = cli_main(
            ["optimize", str(FIXTURES / CHIP),
             "--knob", "avp.vector_width=16,32,64",
             "--knob", "dsb.read_throughput=8,16"],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        assert "improvement" in s
        assert "avp.vector_width" in s

    def test_cli_rejects_knob_without_values(self):
        buf = io.StringIO()
        rc = cli_main(
            ["optimize", str(FIXTURES / CHIP), "--knob", "avp.vector_width=16"],
            out=buf,
        )
        assert rc == 3

    def test_cli_requires_a_knob(self):
        buf = io.StringIO()
        rc = cli_main(["optimize", str(FIXTURES / CHIP)], out=buf)
        assert rc == 3


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
