"""Quiescence early-exit — QEMU-analysis §3.4 的安全加速版本。

真正的 event-skip(跳过纯延迟拍)在轮询型拓扑上是 no-op:每拍总有模块在
yield None 轮询(实测 4000 拍里 3999 拍有 busy)。但另有一个安全加速点:
调度器会跑满 max_cycles,即使 sim 早已排空 —— 排空后只剩空轮询。

run_simulation(stop_at_quiescence=True) 在"无模块 busy + 所有 FIFO 空 +
无存活激励源"时提前停。所有指标在排空点已定型,故结果与跑满 max_cycles
bit-identical。本测试锁住这个等价性。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate
from npu_sim.evaluation.runner import run_simulation
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"

# 覆盖各 plane 的代表 fixture。
_FIXTURES = [
    "usecase_chip_trace_driven.yaml",
    "usecase_npu_v4_full_stack.yaml",
    "usecase_mcu_baseline.yaml",
    "usecase_chip_full_wired.yaml",
    "usecase_l2_256kb.yaml",
]


def _run(name, quiesce, cycles=100000):
    arch = elaborate(str(FIXTURES / name))
    return run_simulation(arch, max_cycles=cycles, stop_at_quiescence=quiesce)


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_quiescence_bit_identical_to_full_run(fixture):
    """早退结果的每个指标 == 跑满 max_cycles 的结果。"""
    q = _run(fixture, quiesce=True)
    f = _run(fixture, quiesce=False)
    assert q.drain_time_ps == f.drain_time_ps
    assert q.total_stall_ps == f.total_stall_ps
    assert q.tokens_delivered == f.tokens_delivered
    assert q.tokens_in_flight == f.tokens_in_flight
    assert q.total_area_um2 == f.total_area_um2
    assert q.per_module_stall_ps == f.per_module_stall_ps
    assert q.bottleneck_module == f.bottleneck_module
    assert q.invariant_report.overall_valid == f.invariant_report.overall_valid


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_quiescence_actually_stops_early(fixture):
    """早退版本用的 cycles ≤ 跑满版本(排空后不再空转)。"""
    q = _run(fixture, quiesce=True)
    f = _run(fixture, quiesce=False)
    assert q.cycles_run <= f.cycles_run


class TestDefaultIsQuiescence:
    def test_default_run_stops_early(self):
        """run_simulation 默认 stop_at_quiescence=True。"""
        arch = elaborate(str(FIXTURES / "usecase_chip_trace_driven.yaml"))
        r = run_simulation(arch, max_cycles=100000)  # 无显式参数
        # 排空在 ~4232,远小于 100000
        assert r.cycles_run < 10000


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
