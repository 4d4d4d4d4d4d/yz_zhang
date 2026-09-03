"""Throughput-aware bottleneck estimate — SPEC-006 §8 cost-model.

逐算子对账证明:pipeline 稳态吞吐由最慢/最忙的模块决定,不是各 op 独立
latency 求和。MappingPlan 现在除 op-serial 求和外,还给出 bottleneck 估算
= 各模块串行总量的 max(busiest module)。当算子跨多个模块时,不同模块可
overlap,bottleneck < op-serial,更贴近真实 pipeline。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import elaborate, estimate_plan, reconcile
from npu_sim.evaluation.runner import run_simulation
from npu_sim.evaluation.trace_ops import load_ops
from npu_sim.reporting import render_mapping_report
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestBottleneckOnMLP:
    """MLP:matmul→MAC(3×),relu→VAU(3×)。MAC 是瓶颈。"""

    @pytest.fixture(scope="class")
    def plan(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_mlp.yaml"))
        ops = load_ops(str(FIXTURES / "usecase_trace_mlp.yaml"))
        return estimate_plan(ops, arch, strict=False)

    def test_bottleneck_module_is_mac(self, plan):
        assert plan.bottleneck_module == "mac"

    def test_per_module_totals_split_correctly(self, plan):
        pm = dict(plan.per_module_cycles)
        assert set(pm) == {"mac", "vau"}
        # 3 matmul on mac, 3 relu on vau
        assert pm["mac"] == plan.bottleneck_cycles
        assert pm["mac"] > pm["vau"]

    def test_bottleneck_below_op_serial_sum(self, plan):
        """跨模块 overlap → bottleneck < op-serial 求和。"""
        assert plan.bottleneck_cycles < plan.total_typical_cycles
        # 具体:mac 315 < sum 363(vau 的 48 拍可与 mac overlap)
        assert plan.bottleneck_cycles == 315
        assert plan.total_typical_cycles == 363


class TestBottleneckEqualsSumWhenSingleModule:
    """attention:6 matmul + 1 softmax,matmul 全在 MAC。"""

    def test_mac_dominates(self):
        arch = elaborate(str(FIXTURES / "usecase_chip_trace_driven.yaml"))
        ops = load_ops(str(FIXTURES / "usecase_trace_attention.yaml"))
        plan = estimate_plan(ops, arch, strict=False)
        # 6 matmul on mac (630) vs 1 softmax on avp (35) → mac bottleneck
        assert plan.bottleneck_module == "mac"
        assert plan.bottleneck_cycles == 630


class TestReconcileReportsBothEstimates:
    def test_summary_has_op_serial_and_bottleneck(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_mlp.yaml"))
        ops = load_ops(str(FIXTURES / "usecase_trace_mlp.yaml"))
        clk = arch.clocks[next(iter(arch.clocks))]
        r = run_simulation(arch, max_cycles=100000)
        rep = reconcile(ops, arch, r.drain_time_ps, clk.period_ps)
        s = rep.summary_text
        assert "op-serial est" in s
        assert "bottleneck est" in s
        assert "ratio measured/bottleneck" in s


class TestMappingReportShowsBottleneck:
    def test_markdown_includes_bottleneck_row(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_mlp.yaml"))
        ops = load_ops(str(FIXTURES / "usecase_trace_mlp.yaml"))
        md = render_mapping_report(estimate_plan(ops, arch, strict=False), arch.name)
        assert "bottleneck cycles" in md
        assert "busiest module `mac`" in md


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
