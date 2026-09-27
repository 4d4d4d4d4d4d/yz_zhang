"""Design-space sweep — the cost of a hardware change (SPEC-003 §7 R7).

Answers "评估硬件变化的代价" by materialising each value as a real override
DSL on the base chip and running it. The headline case sweeps the measured
bottleneck stage (avp.vector_width) and shows both the PPA win and the
diminishing-returns law: past a point the bottleneck shifts to another stage
and further widening stops paying off.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.evaluation import sweep_config
from npu_sim.reporting import render_sweep_report
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"


@pytest.fixture(scope="module")
def report():
    return sweep_config(
        str(FIXTURES / CHIP), "avp", "vector_width", [16, 32, 64]
    )


class TestSweepMechanics:
    def test_one_point_per_value(self, report):
        assert [p.value for p in report.points] == [16, 32, 64]

    def test_base_name_is_the_base_not_the_override(self, report):
        # regression: load_dsl lets a variant name win; base_name must be base
        assert "sweep" not in report.base_name.lower()
        assert "attention" in report.base_name.lower()

    def test_each_point_is_a_real_run(self, report):
        for p in report.points:
            assert p.drain_cycles > 0
            assert p.total_area_um2 > 0

    def test_trace_chip_reports_energy(self, report):
        # the base is a TraceProducer chip, so every point carries total energy
        for p in report.points:
            assert p.total_energy_pj is not None and p.total_energy_pj > 0

    def test_energy_optimum_can_differ_from_drain_optimum(self, report):
        # widening avp cuts drain monotonically, but leakage eventually makes
        # a wider array cost MORE energy than the mid setting — a real PPA
        # tradeoff the energy column surfaces.
        energies = [p.total_energy_pj for p in report.points]
        drains = [p.drain_cycles for p in report.points]
        assert drains[-1] == min(drains)              # widest is drain-optimal
        assert energies.index(min(energies)) != len(energies) - 1  # energy optimum earlier


class TestDiminishingReturns:
    """Widening the bottleneck stage helps — until the bottleneck moves."""

    def test_widening_avp_cuts_drain(self, report):
        d16 = report.points[0].drain_cycles
        d32 = report.points[1].drain_cycles
        assert d32 < d16  # 16→32 is a real win

    def test_bottleneck_shifts_off_avp(self, report):
        # at vw=16 avp is the bottleneck; by vw=64 it has moved elsewhere
        assert report.points[0].bottleneck_module == "avp"
        assert report.points[-1].bottleneck_module != "avp"
        assert report.bottleneck_shifted

    def test_best_value_is_recorded(self, report):
        best_drain = min(p.drain_cycles for p in report.points)
        best_point = next(p for p in report.points if p.value == report.best_value)
        assert best_point.drain_cycles == best_drain

    def test_returns_diminish_after_shift(self, report):
        # 16→32 gain should dwarf 32→64 gain once the bottleneck has moved
        gain_1 = report.points[0].drain_cycles - report.points[1].drain_cycles
        gain_2 = report.points[1].drain_cycles - report.points[2].drain_cycles
        assert gain_1 > gain_2


class TestRenderAndCLI:
    def test_render_flags_shift(self, report):
        md = render_sweep_report(report)
        assert "Design-space sweep" in md
        assert "shifted" in md.lower()
        assert "⭐" in md  # best value marked

    def test_cli_sweep(self):
        buf = io.StringIO()
        rc = cli_main(
            ["sweep", str(FIXTURES / CHIP), "avp.vector_width", "16,32,64"],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        assert "avp.vector_width" in s
        assert "-42%" in s or "-4" in s  # the ~42% win row

    def test_cli_rejects_bad_param(self):
        buf = io.StringIO()
        rc = cli_main(
            ["sweep", str(FIXTURES / CHIP), "no_dot_here", "1,2"],
            out=buf,
        )
        assert rc == 3


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
