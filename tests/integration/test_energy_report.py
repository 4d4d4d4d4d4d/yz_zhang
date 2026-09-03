"""Workload energy report — the "E" of PPA, physically grounded.

Total energy = dynamic (Σ per-op, Horowitz) + static (power × runtime).
Verifies the dynamic term equals the mapped per-op sum, that static is
power×time, and that the attention workload's MAC-dominated breakdown is
correct (6 matmuls × 32³ MACs × 1.1 pJ).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.evaluation import analyze_energy, elaborate, estimate_plan
from npu_sim.evaluation.trace_ops import load_ops
from npu_sim.reporting import render_energy_report
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
TRACE = "usecase_trace_attention.yaml"


class TestEnergyDecomposition:
    @pytest.fixture(scope="class")
    def report(self):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        return analyze_energy(ops, arch)

    def test_total_is_dynamic_plus_static(self, report):
        assert report.total_pj == pytest.approx(report.dynamic_pj + report.static_pj)

    def test_dynamic_matches_mapped_per_op_sum(self, report):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        plan = estimate_plan(ops, arch, strict=False)
        assert report.dynamic_pj == pytest.approx(plan.total_dynamic_pj)

    def test_mac_dominates_and_is_horowitz_grounded(self, report):
        by_mod = dict(report.per_module_pj)
        # 6 matmuls × 32³ MACs × 1.1 pJ/MAC (int8 + fp32 accumulate)
        assert by_mod["mac"] == pytest.approx(6 * 32**3 * 1.1)
        assert by_mod["mac"] > by_mod.get("avp", 0)

    def test_static_is_power_times_runtime(self, report):
        from npu_sim.evaluation import elaborate_and_run
        sim = elaborate_and_run(str(FIXTURES / CHIP), max_cycles=100000)
        expected = sim.total_static_power_uw * sim.drain_time_ps * 1e-6
        assert report.static_pj == pytest.approx(expected, rel=1e-6)

    def test_energy_per_op_positive(self, report):
        assert report.energy_per_op_pj > 0
        assert report.n_ops == 7


class TestRenderAndCLI:
    def test_render_has_ppa_line(self):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        md = render_energy_report(analyze_energy(ops, arch), arch_name="chip")
        assert "Workload energy" in md
        assert "total energy" in md
        assert "Dynamic energy by module" in md

    def test_cli_energy(self):
        buf = io.StringIO()
        rc = cli_main(["energy", str(FIXTURES / CHIP), str(FIXTURES / TRACE)], out=buf)
        assert rc == 0
        s = buf.getvalue()
        assert "total energy" in s
        assert "`mac`" in s


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
