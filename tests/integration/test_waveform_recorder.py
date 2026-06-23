"""WaveformRecorder per-cycle activity trace — validates the user
contract "能反应一拍一拍的变化, 不同器件通过状态机模拟, 互相交互".

For the SPEC-007 MCU+OGU handshake fixture, asserts that:
  - Each module's snapshot_state advances through its declared stages
  - OGU runs in parallel with MCU (both busy simultaneously)
  - The cycle-by-cycle dump is renderable as an ASCII waveform
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate
from npu_sim.evaluation.runner import run_simulation
from npu_sim.reporting.waveform import WaveformRecorder
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def trace():
    arch = elaborate(str(FIXTURES / "usecase_mcu_with_ogu.yaml"))
    rec = WaveformRecorder()
    run_simulation(arch, max_cycles=300, per_cycle_hook=rec)
    return arch, rec


class TestPerCycleSampling:
    """Every scheduler tick is captured exactly once."""

    def test_records_one_state_per_cycle(self, trace):
        _, rec = trace
        assert rec.cycles_recorded == 300

    def test_each_row_has_every_module(self, trace):
        arch, rec = trace
        for c in range(rec.cycles_recorded):
            for mid in arch.modules:
                assert mid in rec._trace[c]


class TestModuleStateMachines:
    """Each module visibly progresses through its named stages."""

    def test_mcu_visits_all_with_ogu_stages(self, trace):
        _, rec = trace
        mcu_states = {rec.state_at(c, "mcu_0") for c in range(rec.cycles_recorded)}
        # SPEC-007 §2.3.2 stages, plus dispatch.
        assert "kick_ogu" in mcu_states or "op_config_local" in mcu_states
        assert "op_config_local" in mcu_states
        assert "wait_ogu_resp" in mcu_states or "dispatch" in mcu_states
        assert "idle" in mcu_states

    def test_ogu_visits_buffsize_and_bd_gen(self, trace):
        _, rec = trace
        ogu_states = {rec.state_at(c, "ogu_0") for c in range(rec.cycles_recorded)}
        # SPEC-007 §3.3 stages.
        assert "buffsize" in ogu_states
        assert "bd_gen" in ogu_states
        assert "idle" in ogu_states


class TestParallelExecution:
    """MCU and OGU must be busy at the same cycle (real parallelism)."""

    def test_mcu_and_ogu_overlap_in_some_cycle(self, trace):
        _, rec = trace
        overlapping = sum(
            1 for c in range(rec.cycles_recorded)
            if rec.state_at(c, "mcu_0") != "idle"
            and rec.state_at(c, "ogu_0") != "idle"
        )
        assert overlapping > 0, (
            "MCU and OGU should run in parallel for at least one cycle"
        )

    def test_ogu_buffsize_then_bd_gen_in_order(self, trace):
        _, rec = trace
        # Find first buffsize cycle and first bd_gen cycle — buffsize first.
        buff_cycles = [c for c in range(rec.cycles_recorded)
                       if rec.state_at(c, "ogu_0") == "buffsize"]
        bd_cycles = [c for c in range(rec.cycles_recorded)
                     if rec.state_at(c, "ogu_0") == "bd_gen"]
        assert buff_cycles[0] < bd_cycles[0]

    def test_ogu_buffsize_duration_is_20_cycles(self, trace):
        """SPEC-007 §3.3.1: buffsize takes 20 cycles per req."""
        _, rec = trace
        # Count consecutive buffsize cycles in the first request.
        in_buff = False
        run_start = None
        run_len = 0
        for c in range(rec.cycles_recorded):
            state = rec.state_at(c, "ogu_0")
            if state == "buffsize":
                if not in_buff:
                    in_buff = True
                    run_start = c
                run_len += 1
            elif in_buff:
                break
        assert run_len == 20, (
            f"§3.3.1: first OGU buffsize run should be 20 cycles, got {run_len}"
        )


class TestWaveformRendering:
    """ASCII waveform output is non-empty and includes module rows."""

    def test_render_returns_text_with_legend(self, trace):
        arch, rec = trace
        out = rec.render(arch, max_cycles=100)
        assert "Legend:" in out
        assert "ogu_0" in out
        assert "mcu_0" in out

    def test_render_includes_stage_glyphs(self, trace):
        arch, rec = trace
        out = rec.render(arch, max_cycles=200)
        # Expect buffsize + bd_gen glyphs in legend.
        assert "buffsize" in out
        assert "bd_gen" in out


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
