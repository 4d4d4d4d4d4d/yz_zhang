"""SPEC-008 §2 OB — output / accumulator buffer YAML+sim evaluation.

Use cases:
  tile_kb sweep      : usecase_ob_small_tile ↔ usecase_ob_large_tile
  double-buffer      : usecase_ob_small_tile ↔ usecase_ob_double_buffer
  fp32_acc cost      : usecase_ob_small_tile ↔ usecase_ob_int32_only
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


class TestOBTileCapacity:
    """SPEC-013: tile_kb × max_in_flight × physical SRAM macro (~2926 µm²/KB)."""

    def test_8kb_to_64kb_grows_area(self):
        report = compare(_run("usecase_ob_small_tile.yaml"),
                         _run("usecase_ob_large_tile.yaml"))
        # (64 - 8) KB × 1 × 2925.7 µm²/KB = 163_840
        assert report.area_delta_um2 == pytest.approx(163_840, abs=2.0)

    def test_double_buffer_doubles_storage_area(self):
        report = compare(_run("usecase_ob_small_tile.yaml"),
                         _run("usecase_ob_double_buffer.yaml"))
        # 8 KB × (2 - 1) × 2925.7 µm²/KB = 23_406
        assert report.area_delta_um2 == pytest.approx(23_406, abs=2.0)


class TestOBFP32Acc:
    """§2.5: fp32_acc capability area = 6_000 μm²."""

    def test_disabling_fp32_drops_capability_area(self):
        report = compare(_run("usecase_ob_small_tile.yaml"),
                         _run("usecase_ob_int32_only.yaml"))
        assert report.area_delta_um2 == pytest.approx(-6_000, abs=1.0)

    def test_capability_set_changes_correctly(self):
        a_full = elaborate(str(FIXTURES / "usecase_ob_small_tile.yaml"))
        a_int32 = elaborate(str(FIXTURES / "usecase_ob_int32_only.yaml"))
        full_caps = set(a_full.modules["ob"].active_capabilities())
        int32_caps = set(a_int32.modules["ob"].active_capabilities())
        assert "fp32_acc" in full_caps and "fp32_acc" not in int32_caps
        assert "int32_acc" in full_caps and "int32_acc" in int32_caps


class TestOBContract:
    def test_ob_registered_with_correct_ports(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "OB" in ModuleRegistry.list_modules()
        a = elaborate(str(FIXTURES / "usecase_ob_small_tile.yaml"))
        ob = a.modules["ob"]
        port_names = {p.name for p in type(ob).port_specs()}
        assert port_names == {"psum_in", "acc_out", "cmd_in"}

    def test_ob_accumulates_psums_and_flushes(self):
        # Elaborate once and reuse the arch for run + introspection so
        # counters survive (elaborate_and_run would build a fresh arch).
        from npu_sim.evaluation.runner import run_simulation
        a = elaborate(str(FIXTURES / "usecase_ob_small_tile.yaml"))
        run_simulation(a, max_cycles=3000)
        ob = a.modules["ob"]
        # With accumulate_depth=1, every psum is its own complete tile.
        assert ob.psums_accepted == ob.flushed_tiles
        assert ob.psums_accepted >= 4


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
