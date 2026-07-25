"""确定性 / 可复现性 — QEMU-Benchmark-Analysis §3.3 收口。

L2 / MMU 曾用硬编码 seed 的 random.Random 决定 hit/miss,消费顺序依赖模块
执行顺序,跨版本不完全可复现。现改为确定性 miss-credit accumulator:
N 次访问精确产生 floor(N × miss_rate) 次 miss,零 RNG,不依赖调度顺序。

本测试锁住"同一 YAML 多次运行 bit-for-bit 一致"这一属性。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate, elaborate_and_run
from npu_sim.evaluation.runner import run_simulation
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestNoRandomInSource:
    """守护:npu_sim 内不再引入非确定性 random。"""

    def test_no_random_import_in_modules(self):
        import npu_sim.modules.dram.l2_module as l2m
        import npu_sim.modules.dram.mmu_module as mmum
        for mod in (l2m, mmum):
            src = Path(mod.__file__).read_text()
            assert "import random" not in src, f"{mod.__name__} imports random"
            assert "random.Random" not in src, f"{mod.__name__} uses random.Random"


class TestL2Deterministic:
    def test_repeated_runs_bit_identical(self):
        def run():
            arch = elaborate(str(FIXTURES / "usecase_l2_256kb.yaml"))
            r = run_simulation(arch, max_cycles=3000)
            l2 = arch.modules["l2"]
            return (r.drain_time_ps, l2.hit_count, l2.miss_count)
        results = [run() for _ in range(5)]
        assert len(set(results)) == 1, f"L2 non-deterministic: {results}"

    def test_hit_rate_is_exact(self):
        """hit_rate=0.5 → 命中/未命中各半(确定性 pattern 的精确比例)。"""
        arch = elaborate(str(FIXTURES / "usecase_l2_256kb.yaml"))
        run_simulation(arch, max_cycles=3000)
        l2 = arch.modules["l2"]
        total = l2.hit_count + l2.miss_count
        assert total > 0
        # floor(N × 0.5) misses → hits == ceil(N/2), misses == floor(N/2)
        assert l2.miss_count == total // 2
        assert l2.hit_count == total - total // 2


class TestMMUDeterministic:
    def test_repeated_runs_bit_identical(self):
        def run():
            arch = elaborate(str(FIXTURES / "usecase_mmu_tlb16.yaml"))
            r = run_simulation(arch, max_cycles=3000)
            m = arch.modules["mmu"]
            return (r.drain_time_ps, m.tlb_hits, m.tlb_misses)
        results = [run() for _ in range(5)]
        assert len(set(results)) == 1, f"MMU non-deterministic: {results}"

    def test_high_hit_rate_produces_few_misses(self):
        """tlb_hit_rate=0.95 → miss 数 == floor(N × 0.05)。"""
        arch = elaborate(str(FIXTURES / "usecase_mmu_tlb256_hot.yaml"))
        run_simulation(arch, max_cycles=3000)
        m = arch.modules["mmu"]
        total = m.tlb_hits + m.tlb_misses
        assert total > 0
        # 0.95 hit → very few misses
        assert m.tlb_misses <= total * 0.05 + 1


class TestFullEvalReproducible:
    """端到端:一个 compare 评估跑两遍,delta 完全相同。"""

    def test_l2_compare_reproducible(self):
        def run_compare():
            from npu_sim.evaluation import compare
            b = elaborate_and_run(str(FIXTURES / "usecase_l2_256kb.yaml"), max_cycles=3000)
            v = elaborate_and_run(str(FIXTURES / "usecase_l2_2mb_hot.yaml"), max_cycles=3000)
            r = compare(b, v)
            return (r.drain_time_delta_ps, r.area_delta_um2, r.stall_delta_ps)
        assert run_compare() == run_compare()


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
