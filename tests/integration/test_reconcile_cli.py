"""CLI `reconcile` — 把 SPEC-006 静态映射估算与仿真实测 drain join。

`estimate` 只给静态下界;`reconcile` 再跑一遍仿真,把 Mapper 估的
op-serial / bottleneck 周期与实测 drain(以及 sink 逐 op 到达间隔)并列,
量化估算 gap(SPEC-006 §8 estimate-vs-measured)。这个子命令把之前只有
Python-API 的对账流程暴露到命令行。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
TRACE = "usecase_trace_attention.yaml"


class TestReconcileCLI:
    def test_reports_both_estimates_and_measured(self):
        buf = io.StringIO()
        rc = cli_main(
            ["reconcile", str(FIXTURES / CHIP), str(FIXTURES / TRACE)],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        # 头部对账表:两种估算 + 实测 + 双 ratio
        assert "Estimate vs measured" in s
        assert "op-serial estimate" in s
        assert "bottleneck estimate" in s
        assert "measured drain" in s
        assert "ratio measured / op-serial" in s
        assert "ratio measured / bottleneck" in s

    def test_per_module_and_per_op_tables_present(self):
        buf = io.StringIO()
        cli_main(
            ["reconcile", str(FIXTURES / CHIP), str(FIXTURES / TRACE)],
            out=buf,
        )
        s = buf.getvalue()
        assert "Per-module serial work" in s
        assert "Per-op estimate vs measured" in s
        # 7-op attention → mac / avp 承担计算
        assert "`mac`" in s
        assert "`avp`" in s

    def test_explicit_sink_flag(self):
        buf = io.StringIO()
        rc = cli_main(
            [
                "reconcile",
                str(FIXTURES / CHIP),
                str(FIXTURES / TRACE),
                "--sink",
                "sink",
            ],
            out=buf,
        )
        assert rc == 0
        assert "Per-op estimate vs measured" in buf.getvalue()

    def test_writes_to_out_file(self, tmp_path):
        out_file = tmp_path / "reconcile.md"
        buf = io.StringIO()
        rc = cli_main(
            [
                "reconcile",
                str(FIXTURES / CHIP),
                str(FIXTURES / TRACE),
                "--out",
                str(out_file),
            ],
            out=buf,
        )
        assert rc == 0
        assert out_file.exists()
        assert "Estimate vs measured" in out_file.read_text()
        # stdout stayed empty when --out is given
        assert buf.getvalue() == ""

    def test_ops_from_standalone_file(self, tmp_path):
        ops_file = tmp_path / "ops.yaml"
        ops_file.write_text(
            "ops:\n"
            "  - { op_type: matmul, m: 32, k: 32, n: 32, precision: int8 }\n"
            "  - { op_type: matmul, m: 32, k: 32, n: 32, precision: int8 }\n"
        )
        buf = io.StringIO()
        rc = cli_main(
            ["reconcile", str(FIXTURES / CHIP), str(ops_file)],
            out=buf,
        )
        assert rc == 0
        assert "ops mapped" in buf.getvalue()


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
