"""Estimate-vs-measured 对账 — SPEC-006 §8 候选落地。

同一算子 trace:RuleBasedMapper 静态估的总周期(op-serial,无 overlap /
反压)vs 仿真实测的 drain(cycles)。reconcile() 把两者 join,量化差异,
作为估算模型校准的依据。

也验证了一个之前的 Mapper bug 修复:激励/基础设施模块(TraceProducer/
Producer/NoC/PMU…)的 can_execute 无脑返回 True,曾导致算子被误映射到
trace_src;现在 Mapper 用 required_capabilities ⊆ active_capabilities
的权威判据过滤。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import (
    elaborate,
    elaborate_and_run,
    estimate_plan,
    reconcile,
)
from npu_sim.evaluation.trace_ops import load_ops
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
TRACE = "usecase_trace_attention.yaml"


class TestMapperRoutesToComputeModules:
    """回归:算子不再被误映射到激励源。"""

    def test_matmul_routes_to_mac_not_trace_src(self):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        plan = estimate_plan(ops, arch, strict=False)
        routing = {d.op_index: d.module_id for d in plan.decisions}
        # 7 ops:6 matmul → mac,1 softmax → avp
        assert all(
            routing[i] == "mac"
            for i, o in enumerate(ops) if o.op_type == "matmul"
        )
        assert any(mid == "avp" for mid in routing.values())
        assert "trace_src" not in routing.values()

    def test_stimulus_module_never_a_compute_target(self):
        """TraceProducer 的 trace_replay 能力不覆盖任何计算算子。"""
        arch = elaborate(str(FIXTURES / TRACE))  # trace_src + cons only
        ops = load_ops(str(FIXTURES / TRACE))
        # 该 arch 没有 MAC/AVP,故全部 unmapped(strict=False)——关键是
        # 不会错误地映射到 trace_src。
        plan = estimate_plan(ops, arch, strict=False)
        assert plan.decisions == ()
        assert len(plan.unmapped) == len(ops)


class TestReconcile:
    """estimate vs measured join。"""

    @pytest.fixture(scope="class")
    def report(self):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        clk = arch.clocks[next(iter(arch.clocks))]
        sim = elaborate_and_run(str(FIXTURES / CHIP), max_cycles=100000)
        return reconcile(
            ops, arch,
            measured_drain_ps=sim.drain_time_ps,
            clock_period_ps=clk.period_ps,
        )

    def test_estimate_is_lower_bound(self, report):
        """静态估(op-serial,无 overlap/反压)应 ≤ 实测 drain。"""
        assert report.estimate_cycles <= report.measured_cycles
        assert report.ratio >= 1.0

    def test_all_ops_mapped(self, report):
        assert report.plan.unmapped == ()
        assert len(report.plan.decisions) == 7

    def test_abs_error_is_measured_minus_estimate(self, report):
        assert report.abs_error_cycles == (
            report.measured_cycles - report.estimate_cycles
        )

    def test_summary_mentions_both_numbers(self, report):
        s = report.summary_text
        assert "static estimate" in s
        assert "measured drain" in s
        assert "ratio" in s


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
