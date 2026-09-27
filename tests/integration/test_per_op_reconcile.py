"""Per-op estimate-vs-measured 对账 — SPEC-006 §8 v1.1 落地。

链级对账(reconcile)只给一个总比值。逐算子对账把每个算子的 Mapper 估算
与它在 sink 的到达时间 join:trace token 带 op_index(SPEC-012),穿过整条
通路被各模块 {**metadata} 保留,故 sink 能按 op 还原到达拍。

揭示的洞察:pipeline 稳态吞吐由最慢 stage 决定,不是各 op 独立 latency
—— softmax 估 35 拍但稳态 512 拍(被 MAC 主导),这是"op-serial 估算模型"
与"真实 pipeline"的本质差异,正是校准要量化的对象。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import (
    elaborate,
    reconcile_per_op,
    sink_op_arrivals,
)
from npu_sim.evaluation.runner import run_simulation
from npu_sim.evaluation.trace_ops import load_ops
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
TRACE = "usecase_trace_attention.yaml"


class TestSinkOpArrivals:
    def test_op_index_preserved_to_sink(self):
        arch = elaborate(str(FIXTURES / CHIP))
        run_simulation(arch, max_cycles=100000)
        arrivals = sink_op_arrivals(arch, "sink")
        # 7 attention ops arrive, indices 0..6 in order.
        assert [op for op, _ in arrivals] == [0, 1, 2, 3, 4, 5, 6]
        # arrivals strictly increasing.
        times = [t for _, t in arrivals]
        assert times == sorted(times)
        assert len(set(times)) == 7


class TestPerOpReconcile:
    @pytest.fixture(scope="class")
    def report(self):
        arch = elaborate(str(FIXTURES / CHIP))
        run_simulation(arch, max_cycles=100000)
        ops = load_ops(str(FIXTURES / TRACE))
        clk = arch.clocks[next(iter(arch.clocks))]
        arrivals = sink_op_arrivals(arch, "sink")
        return reconcile_per_op(ops, arch, arrivals, clk.period_ps)

    def test_one_row_per_op(self, report):
        assert len(report.rows) == 7

    def test_rows_carry_routing(self, report):
        by_idx = {r.op_index: r for r in report.rows}
        assert by_idx[0].module_id == "mac"     # matmul → mac
        assert by_idx[4].module_id == "avp"     # softmax → avp

    def test_measured_at_least_estimate(self, report):
        """每个 op 的实测(到达间隔)≥ 静态估(下界性质在 op 级也成立)。"""
        for r in report.rows:
            assert r.measured_cycles >= r.estimate_cycles
            assert r.ratio >= 1.0

    def test_steady_state_gap_is_uniform(self, report):
        """稳态段(op1..6)的到达间隔一致 —— pipeline 吞吐由最慢 stage 定。"""
        steady = [r.measured_cycles for r in report.rows if r.op_index >= 1]
        assert len(set(steady)) == 1, f"non-uniform steady-state: {steady}"

    def test_softmax_measured_dominated_by_pipeline_not_its_latency(self, report):
        """softmax 估 35 但稳态吞吐远大于 35 —— 证明它受 pipeline 主导。"""
        sm = next(r for r in report.rows if r.op_type == "softmax")
        assert sm.estimate_cycles == 35
        assert sm.measured_cycles > sm.estimate_cycles * 3

    def test_summary_is_a_table(self, report):
        s = report.summary_text
        assert "est cyc" in s and "measured cyc" in s and "ratio" in s


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
