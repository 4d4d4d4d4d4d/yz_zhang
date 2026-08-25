"""SPEC-011 DRAM + specialized — MC / L2 / SE / TLU / CMDQ / MMU evaluations."""

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


class TestMC:
    def test_more_banks_grows_area(self):
        r = _cmp("usecase_mc_8banks.yaml", "usecase_mc_16banks.yaml")
        # (16-8) × 8000 = 64_000
        assert r.area_delta_um2 == pytest.approx(64_000, abs=200)


class TestL2:
    def test_larger_cache_grows_area(self):
        r = _cmp("usecase_l2_256kb.yaml", "usecase_l2_2mb_hot.yaml")
        # SPEC-013 physical SRAM macro: (2048-256) KB × 2925.7 µm²/KB = 5_242_880
        assert r.area_delta_um2 == pytest.approx(5_242_880, abs=1000)


class TestSE:
    def test_structured_pruning_adds_area(self):
        r = _cmp("usecase_se_30pct.yaml", "usecase_se_80pct_structured.yaml")
        # +8_000 structured cap
        assert r.area_delta_um2 == pytest.approx(8_000, abs=100)

    def test_higher_sparsity_speeds_up_drain(self):
        r = _cmp("usecase_se_30pct.yaml", "usecase_se_80pct_structured.yaml")
        # 80% sparsity + structured → much less work
        assert r.drain_time_delta_ps < 0


class TestTLU:
    def test_larger_table_grows_area(self):
        r = _cmp("usecase_tlu_512kb.yaml", "usecase_tlu_8mb.yaml")
        # (8192-512) × 600 + 4_000 scatter = 4_612_000
        assert r.area_delta_um2 == pytest.approx(4_612_000, abs=500)


class TestCMDQ:
    def test_deeper_priority_grows_area(self):
        r = _cmp("usecase_cmdq_16.yaml", "usecase_cmdq_256_priority.yaml")
        # SPEC-013 register file (8B/entry flops) + priority arbiter gates:
        # (256-16) entries × 320 µm² + 1200 arbiter = 62_640
        assert r.area_delta_um2 == pytest.approx(62_640, abs=200)


class TestMMU:
    def test_larger_tlb_grows_area(self):
        r = _cmp("usecase_mmu_tlb16.yaml", "usecase_mmu_tlb256_hot.yaml")
        # SPEC-013 TLB CAM (8B/entry × 2.5× SRAM): (256-16) × ~57 µm² = 13_714
        assert r.area_delta_um2 == pytest.approx(13_714, abs=100)

    def test_higher_hit_rate_speeds_up_drain(self):
        r = _cmp("usecase_mmu_tlb16.yaml", "usecase_mmu_tlb256_hot.yaml")
        assert r.drain_time_delta_ps < 0


class TestSPEC011Contract:
    def test_all_6_modules_registered(self):
        from npu_sim.core.module_registry import ModuleRegistry
        registered = set(ModuleRegistry.list_modules())
        for mid in ("MC", "L2", "SE", "TLU", "CMDQ", "MMU"):
            assert mid in registered, f"{mid} not registered"


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
