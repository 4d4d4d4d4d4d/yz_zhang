"""SPEC-008 §1 WB — weight buffer YAML+sim evaluation.

Drives the three §1.8 use cases:
  capacity sweep   : usecase_wb_small_capacity ↔ usecase_wb_large_capacity
  prefetch on/off  : usecase_wb_small_capacity ↔ usecase_wb_prefetch
  overflow         : usecase_wb_small_capacity ↔ usecase_wb_overflow
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _run(name: str, cycles: int = 3000):
    return elaborate_and_run(str(FIXTURES / name), max_cycles=cycles)


class TestWBCapacitySweep:
    """SPEC-013: area scales with capacity via the physical SRAM macro (~2926 µm²/KB)."""

    def test_capacity_quadruples_area(self):
        base = _run("usecase_wb_small_capacity.yaml")
        var = _run("usecase_wb_large_capacity.yaml")
        report = compare(base, var)
        # 64 KB → 256 KB = +192 KB × 2925.7 µm²/KB (SPEC-013 SRAM macro)
        assert report.area_delta_um2 == pytest.approx(561_737, abs=2.0), (
            f"§1.5.1: capacity-scaled area delta wrong: {report.area_delta_um2}"
        )

    def test_capacity_change_preserves_drain_time(self):
        """Same workload fits both — drain should be identical."""
        base = _run("usecase_wb_small_capacity.yaml")
        var = _run("usecase_wb_large_capacity.yaml")
        assert base.drain_time_ps == var.drain_time_ps


class TestWBPrefetchBenefit:
    """§1.4.3 prefetch capability flag → +area, same drain (no prefetch traffic)."""

    def test_enable_prefetch_adds_capability_area(self):
        base = _run("usecase_wb_small_capacity.yaml")
        var = _run("usecase_wb_prefetch.yaml")
        report = compare(base, var)
        # weight_prefetch capability area_cost_um2 = 4000.
        assert report.area_delta_um2 == pytest.approx(4_000, abs=1.0)

    def test_prefetch_capability_active(self):
        arch = elaborate(str(FIXTURES / "usecase_wb_prefetch.yaml"))
        caps = set(arch.modules["wb"].active_capabilities())
        assert "weight_prefetch" in caps
        # Baseline does NOT have it.
        arch_b = elaborate(str(FIXTURES / "usecase_wb_small_capacity.yaml"))
        assert "weight_prefetch" not in arch_b.modules["wb"].active_capabilities()


class TestWBOverflow:
    """§1.4.4 / §1.7.1: small capacity + large workload → overflow path."""

    def test_overflow_serves_fewer_tiles(self):
        """With 4 KB capacity vs 8 × 1 KB workload, WB can hold at most 4
        tiles → only 4 serves vs baseline's 8."""
        arch_base = elaborate(str(FIXTURES / "usecase_wb_small_capacity.yaml"))
        elaborate_and_run(str(FIXTURES / "usecase_wb_small_capacity.yaml"), max_cycles=3000)
        served_base = arch_base.modules["wb"].weights_served

        arch_var = elaborate(str(FIXTURES / "usecase_wb_overflow.yaml"))
        elaborate_and_run(str(FIXTURES / "usecase_wb_overflow.yaml"), max_cycles=3000)
        served_var = arch_var.modules["wb"].weights_served

        # Baseline (64 KB) fits all 8 tiles; variant (4 KB) overflows after 4.
        assert served_base >= served_var, (
            f"Overflow variant should serve ≤ baseline; "
            f"baseline {served_base}, variant {served_var}"
        )
        assert served_var <= 4, (
            f"4 KB capacity / 1 KB per tile should fit ≤4 tiles; got {served_var}"
        )

    def test_overflow_area_smaller(self):
        base = _run("usecase_wb_small_capacity.yaml")
        var = _run("usecase_wb_overflow.yaml")
        report = compare(base, var)
        # 64 KB → 4 KB = -60 KB × 2925.7 µm²/KB (SPEC-013 SRAM macro)
        assert report.area_delta_um2 == pytest.approx(-175_543, abs=2.0)


class TestWBContract:
    """SPEC-001 §6 conformance: registration + port specs + estimate_area."""

    def test_wb_registered(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "WB" in ModuleRegistry.list_modules()

    def test_wb_ports_match_spec(self):
        arch = elaborate(str(FIXTURES / "usecase_wb_small_capacity.yaml"))
        wb = arch.modules["wb"]
        port_names = {p.name for p in type(wb).port_specs()}
        # §1.3.1-4
        assert port_names == {"weight_in", "weight_out", "prefetch_cmd_in", "cmd_in"}

    def test_area_scales_with_capacity_in_sim(self):
        """SPEC-013: 256 KB WB contributes ~749k µm² (physical SRAM macro).
        Derived via sim total_area_um2 to honor the YAML-driven contract."""
        result = _run("usecase_wb_large_capacity.yaml")
        # WB is the dominant area contributor (Producer/Consumer are virtual).
        # 256 KB × 2925.7 µm²/KB = ~749k µm² for storage + small capability extras.
        assert result.total_area_um2 >= 748_000, (
            f"total_area_um2 = {result.total_area_um2} below WB capacity floor"
        )


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
