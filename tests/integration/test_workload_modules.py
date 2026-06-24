"""SPEC-009 Tier 2 — IM2COL / RDC / NoC / CDE / Transpose evaluations.

Compact suite covering each module's headline knob via YAML+sim compare.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
import npu_sim.modules  # noqa: F401
from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _cmp(b, v, cycles=3000):
    return compare(
        elaborate_and_run(str(FIXTURES / b), max_cycles=cycles),
        elaborate_and_run(str(FIXTURES / v), max_cycles=cycles),
    )


class TestIM2COL:
    def test_3x3_costs_more_than_1x1(self):
        r = _cmp("usecase_im2col_1x1.yaml", "usecase_im2col_3x3.yaml")
        # 3×3 vs 1×1 → kernel area ratio 9; drain should grow ≥4× per token.
        assert r.drain_time_delta_ps > 0
        assert r.both_valid

    def test_im2col_registered_and_has_ports(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "IM2COL" in ModuleRegistry.list_modules()
        a = elaborate(str(FIXTURES / "usecase_im2col_1x1.yaml"))
        assert {p.name for p in type(a.modules["im"]).port_specs()} == \
               {"act_in", "kernel_desc_in", "im2col_out"}


class TestRDC:
    def test_wider_tree_grows_area(self):
        r = _cmp("usecase_rdc_small.yaml", "usecase_rdc_wide.yaml")
        # 4 → 16 width: storage 12k × (16-4)/8 = +18k
        assert r.area_delta_um2 == pytest.approx(18_000, abs=200)


class TestNoC:
    def test_slow_route_increases_drain(self):
        r = _cmp("usecase_noc_unicast.yaml", "usecase_noc_slow.yaml")
        # route_cycles 2 → 4 = +2 cycles per routed packet.
        assert r.drain_time_delta_ps > 0
        assert r.both_valid


class TestCDE:
    def test_zlib_adds_area(self):
        r = _cmp("usecase_cde_05.yaml", "usecase_cde_zlib.yaml")
        # compress_rle 20k → compress_zlib 30k = +10k
        assert r.area_delta_um2 == pytest.approx(10_000, abs=100)


class TestTranspose:
    def test_3d_adds_capability_area(self):
        r = _cmp("usecase_transpose_2d.yaml", "usecase_transpose_3d.yaml")
        # layout_transform_3d = +5_000
        assert r.area_delta_um2 == pytest.approx(5_000, abs=100)


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
