"""CLI `estimate` + MappingPlan 报告渲染 — 把算子 trace 静态映射到架构。

连接 SPEC-012(trace = 算子序列)与 SPEC-006(Mapper:算子→模块)。
同一个 trace 文件既能驱动 TraceProducer 做动态仿真,也能喂 Mapper 做静态
估算(SPEC-006 §8 estimate-vs-measured 的基础)。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.cli import main as cli_main
from npu_sim.evaluation import elaborate, estimate_plan
from npu_sim.evaluation.trace_ops import load_ops, ops_from_list
from npu_sim.reporting import render_mapping_report
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestTraceOpsLoader:
    def test_op_type_capability_mapping(self):
        ops = ops_from_list([
            {"op_type": "matmul", "m": 32, "k": 32, "n": 32, "precision": "int8"},
            {"op_type": "matmul", "m": 8, "k": 8, "n": 8, "precision": "bf16"},
            {"op_type": "softmax", "n_elements": 256},
            {"op_type": "relu", "n_elements": 128},
        ])
        assert ops[0].required_capabilities == ["int8_matmul"]
        assert ops[1].required_capabilities == ["bfp16_matmul"]  # bf16 → bfp16 lane
        assert ops[2].required_capabilities == ["softmax"]
        assert ops[3].required_capabilities == ["relu"]
        # shape carried through
        assert ops[0].shape_info["m"] == 32

    def test_load_from_trace_fixture(self):
        """能直接复用 SPEC-012 的 TraceProducer fixture 的 config.ops。"""
        ops = load_ops(str(FIXTURES / "usecase_trace_attention.yaml"))
        assert len(ops) == 7  # attention block
        assert all(o.op_type in ("matmul", "softmax") for o in ops)


class TestEstimatePlanRouting:
    def test_attention_ops_route_to_expected_modules(self):
        arch = elaborate(str(FIXTURES / "npu_pipeline.yaml"))
        ops = ops_from_list([
            {"op_type": "matmul", "m": 32, "k": 32, "n": 32, "precision": "int8"},
            {"op_type": "softmax", "n_elements": 256},
            {"op_type": "relu", "n_elements": 128},
        ])
        plan = estimate_plan(ops, arch)
        routing = {d.op_type: d.module_id for d in plan.decisions}
        assert routing["matmul"] == "mac"
        assert routing["softmax"] == "avp"
        assert routing["relu"] == "vau"
        assert plan.unmapped == ()
        assert plan.total_typical_cycles > 0


class TestMappingReportRender:
    def test_report_has_routing_and_totals(self):
        arch = elaborate(str(FIXTURES / "npu_pipeline.yaml"))
        ops = ops_from_list([
            {"op_type": "matmul", "m": 32, "k": 32, "n": 32, "precision": "int8"},
        ])
        md = render_mapping_report(estimate_plan(ops, arch), arch_name=arch.name)
        assert "Mapping estimate" in md
        assert "Routing" in md
        assert "mac" in md
        assert "all ops mapped" in md


class TestEstimateCLI:
    def test_estimate_from_standalone_ops_file(self, tmp_path):
        ops_file = tmp_path / "ops.yaml"
        ops_file.write_text(
            "ops:\n"
            "  - { op_type: matmul, m: 32, k: 32, n: 32, precision: int8 }\n"
            "  - { op_type: softmax, n_elements: 256 }\n"
        )
        buf = io.StringIO()
        rc = cli_main(
            ["estimate", str(FIXTURES / "npu_pipeline.yaml"), str(ops_file)],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        assert "ops mapped | 2" in s
        assert "**mac**" in s and "**avp**" in s

    def test_estimate_reuses_trace_fixture(self):
        buf = io.StringIO()
        rc = cli_main(
            [
                "estimate",
                str(FIXTURES / "npu_pipeline.yaml"),
                str(FIXTURES / "usecase_trace_attention.yaml"),
            ],
            out=buf,
        )
        assert rc == 0
        assert "ops mapped | 7" in buf.getvalue()


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
