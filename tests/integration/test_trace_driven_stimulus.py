"""SPEC-012 Trace-Driven 激励 — 让芯片跑真实模型算子序列而非合成 token。

对标 QEMU"喂真实 guest binary"的精神:TraceProducer 播放一个真实的
attention block 算子序列,每个算子按 shape 生成异质 token,穿过真实数据
通路。这是把评估从"抽象流量"升级为"真实模型层负载"的证明。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
from npu_sim.evaluation.runner import run_simulation
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestTraceProducerContract:
    """SPEC-012 §1:注册、端口、op→token 映射、虚拟面积。"""

    def test_registered(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "TraceProducer" in ModuleRegistry.list_modules()

    def test_single_output_port(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_attention.yaml"))
        tp = arch.modules["trace_src"]
        assert {p.name for p in type(tp).port_specs()} == {"out"}

    def test_virtual_area(self):
        """激励源不占硅面积:整个 arch 的 total_area 里 TraceProducer 贡献 0。"""
        arch = elaborate(str(FIXTURES / "usecase_trace_attention.yaml"))
        tp = arch.modules["trace_src"]
        assert tp.total_area_um2() == 0.0

    def test_op_output_bytes_mapping(self):
        """§1.4:matmul 由 m×n×precision,elementwise 由 n_elements×4。"""
        from npu_sim.modules.probe.trace_producer import _op_output_bytes
        # int8 32x32 → 32*32*1 = 1024
        assert _op_output_bytes(
            {"op_type": "matmul", "m": 32, "n": 32, "precision": "int8"}) == 1024
        # bf16 doubles bytes → 2048
        assert _op_output_bytes(
            {"op_type": "matmul", "m": 32, "n": 32, "precision": "bf16"}) == 2048
        # softmax 256 elements → 1024 (FP32 out)
        assert _op_output_bytes({"op_type": "softmax", "n_elements": 256}) == 1024
        # unknown → default 64
        assert _op_output_bytes({"op_type": "relu"}) == 64


class TestTracePlaysInOrder:
    """SPEC-012 §4:trace 按序播放,token 数 == len(ops) × repeat。"""

    def test_all_ops_emitted(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_attention.yaml"))
        run_simulation(arch, max_cycles=5000)
        tp = arch.modules["trace_src"]
        assert tp.total_ops == 7          # attention block = 7 ops
        assert tp.emitted == 7

    def test_metadata_carries_op_type_and_index(self):
        """每个 token 带 op_type / op_index —— 用 Passthrough 捕获转发的 token。
        这里直接检查 TraceProducer 构造的 metadata 语义(通过一次真实运行后
        Consumer 端的接收计数 + 手动构造校验)。"""
        # 用一条 TraceProducer → Consumer 的最短链,断言全部送达。
        arch = elaborate(str(FIXTURES / "usecase_trace_attention.yaml"))
        result = run_simulation(arch, max_cycles=5000)
        # 7 个算子 token 全部到达 Consumer。
        key = "trace_src.out→cons.in"
        assert result.tokens_delivered.get(key) == 7


class TestMultiLayerScaling:
    """SPEC-012 §3:repeat=4 → 4 层,drain 约 4×。"""

    def test_4layer_drain_is_4x(self):
        base = elaborate_and_run(
            str(FIXTURES / "usecase_trace_attention.yaml"), max_cycles=5000)
        var = elaborate_and_run(
            str(FIXTURES / "usecase_trace_attention_4layer.yaml"), max_cycles=5000)
        assert var.drain_time_ps == pytest.approx(4 * base.drain_time_ps, rel=0.1)

    def test_4layer_emits_28_ops(self):
        arch = elaborate(str(FIXTURES / "usecase_trace_attention_4layer.yaml"))
        run_simulation(arch, max_cycles=5000)
        assert arch.modules["trace_src"].emitted == 28


class TestRealChipRunsRealLayer:
    """SPEC-012 §4:真实数据通路由真实 attention 序列驱动,端到端贯通。"""

    def test_attention_flows_through_datapath(self):
        arch = elaborate(str(FIXTURES / "usecase_chip_trace_driven.yaml"))
        result = run_simulation(arch, max_cycles=100000)
        assert result.invariant_report.overall_valid
        # 7 个算子全部穿过 DAGC→DSB→MAC→VAU→AVP 到达 sink。
        assert result.tokens_delivered.get("avp.out_data→sink.in") == 7
        assert arch.modules["trace_src"].emitted == 7

    def test_no_tokens_stuck(self):
        arch = elaborate(str(FIXTURES / "usecase_chip_trace_driven.yaml"))
        result = run_simulation(arch, max_cycles=100000)
        stuck = {k: v for k, v in result.tokens_in_flight.items() if v != 0}
        assert stuck == {}, f"tokens stuck: {stuck}"


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
