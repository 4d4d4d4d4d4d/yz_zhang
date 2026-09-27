"""SPEC-008 §4 SFU — special function unit YAML+sim evaluation.

Use cases:
  trig cost          : usecase_sfu_baseline ↔ usecase_sfu_trig_enabled
  op-latency sweep   : usecase_sfu_baseline (exp, 8c) ↔ usecase_sfu_div (14c)
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


class TestSFUTrigCost:
    """§4.5.1: enable_trig adds sin+cos capabilities = +8_000 μm²."""

    def test_enable_trig_adds_area(self):
        report = compare(_run("usecase_sfu_baseline.yaml"),
                         _run("usecase_sfu_trig_enabled.yaml"))
        # sin (4000) + cos (4000) = 8_000
        assert report.area_delta_um2 == pytest.approx(8_000, abs=1.0)

    def test_capability_set_grows(self):
        a_base = elaborate(str(FIXTURES / "usecase_sfu_baseline.yaml"))
        a_trig = elaborate(str(FIXTURES / "usecase_sfu_trig_enabled.yaml"))
        base_caps = set(a_base.modules["sfu"].active_capabilities())
        trig_caps = set(a_trig.modules["sfu"].active_capabilities())
        assert {"sin", "cos"}.issubset(trig_caps)
        assert {"sin", "cos"}.isdisjoint(base_caps)


class TestSFUOpLatencySweep:
    """§4.4.1: div (14c) vs exp (8c) → +6c per token over N tokens."""

    def test_div_is_slower_than_exp(self):
        report = compare(_run("usecase_sfu_baseline.yaml"),
                         _run("usecase_sfu_div.yaml"))
        # 6 tokens × 6 extra cycles = 36 cycles × 1000 ps = +36_000 ps
        assert report.drain_time_delta_ps == pytest.approx(36_000, abs=2_000)

    def test_div_keeps_same_area(self):
        report = compare(_run("usecase_sfu_baseline.yaml"),
                         _run("usecase_sfu_div.yaml"))
        # default_op change doesn't move capabilities → area unchanged
        assert report.area_delta_um2 == pytest.approx(0, abs=1.0)


class TestSFUContract:
    def test_sfu_registered_with_ports(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "SFU" in ModuleRegistry.list_modules()
        a = elaborate(str(FIXTURES / "usecase_sfu_baseline.yaml"))
        sfu = a.modules["sfu"]
        port_names = {p.name for p in type(sfu).port_specs()}
        assert port_names == {"req_in", "operand_in", "result_out"}


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
