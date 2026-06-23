"""SPEC-008 §3 Quant — quant/dequant YAML+sim evaluation.

Use cases:
  per-channel cost   : usecase_quant_baseline ↔ usecase_quant_per_channel
  direction sweep    : usecase_quant_baseline ↔ usecase_dequant
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _run(name, cycles=3000):
    return elaborate_and_run(str(FIXTURES / name), max_cycles=cycles)


class TestQuantPerChannelCost:
    """§3.7: per_channel = +3500 μm² (4000 channel - 500 tensor), +1 cycle/token."""

    def test_per_channel_adds_area(self):
        report = compare(_run("usecase_quant_baseline.yaml"),
                         _run("usecase_quant_per_channel.yaml"))
        # per_channel_scale 4000 - per_tensor_scale 500 = +3500
        assert report.area_delta_um2 == pytest.approx(3_500, abs=1.0)

    def test_per_channel_adds_one_cycle_per_token(self):
        report = compare(_run("usecase_quant_baseline.yaml"),
                         _run("usecase_quant_per_channel.yaml"))
        # 4 tokens × 1 extra cycle × 1000 ps = +4000 ps
        assert report.drain_time_delta_ps == pytest.approx(4_000, abs=1_000)


class TestQuantDirectionSweep:
    """§3.7 direction: quant shrinks 4×, dequant expands 4×."""

    def test_direction_changes_capability_set(self):
        a_q = elaborate(str(FIXTURES / "usecase_quant_baseline.yaml"))
        a_dq = elaborate(str(FIXTURES / "usecase_dequant.yaml"))
        q_caps = set(a_q.modules["q"].active_capabilities())
        dq_caps = set(a_dq.modules["q"].active_capabilities())
        assert "fp32_to_int8" in q_caps and "fp32_to_int8" not in dq_caps
        assert "int8_to_fp32" in dq_caps and "int8_to_fp32" not in q_caps


class TestQuantContract:
    def test_quant_registered(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "Quant" in ModuleRegistry.list_modules()

    def test_invalid_direction_rejected(self):
        from npu_sim.core.errors import ConfigurationError
        from npu_sim.core.module_registry import ModuleRegistry
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
        from npu_sim.architecture.clock import SimpleClock

        # Direct config validation via registry-created module.
        cls = ModuleRegistry._registry["Quant"]
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        clock = SimpleClock("global", period_ps=1000)
        m = cls()
        m.bind_services(event_bus=bus, stat_sink=sink, clock=clock)
        with pytest.raises(ConfigurationError):
            m.configure({"direction": "garbage"})


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
