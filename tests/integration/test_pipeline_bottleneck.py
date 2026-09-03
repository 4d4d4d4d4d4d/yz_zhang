"""Measured pipeline-bottleneck attribution — SPEC-006 §8 throughput model.

reconcile.py showed the static Mapper estimate runs 5–15× under measured
drain. This explains it with ground truth: every token streams through every
stage, so throughput is set by the slowest *stage on the path*, not by where
the Mapper routed the op. The headline test pins the discrepancy — the static
Mapper calls `mac` the bottleneck, but the measured pipeline bottleneck is
`avp` — and shows the pipeline formula reconciles measured drain to <1%.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import (
    analyze_pipeline_bottleneck,
    elaborate,
    estimate_plan,
)
from npu_sim.evaluation.trace_ops import load_ops
from npu_sim.reporting import render_pipeline_bottleneck
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
TRACE = "usecase_trace_attention.yaml"


@pytest.fixture(scope="module")
def report():
    """One measured run shared across the module (each run is a full sim)."""
    return analyze_pipeline_bottleneck(elaborate(str(FIXTURES / CHIP)))


class TestBottleneckAttribution:
    def test_bottleneck_is_avp(self, report):
        assert report.bottleneck_module == "avp"
        assert report.bottleneck_ii == pytest.approx(512, abs=1)

    def test_every_stage_sees_all_tokens(self, report):
        # 7-op attention trace → all datapath stages process 7 tokens
        assert {s.tokens_through for s in report.stages} == {7}

    def test_stages_sorted_by_ii_descending(self, report):
        iis = [s.service_ii for s in report.stages]
        assert iis == sorted(iis, reverse=True)

    def test_dominant_stage_named(self, report):
        top = report.stages[0]
        assert top.module_id == "avp"
        assert top.dominant_stage == "lut_lookup"

    def test_model_reconciles_measured_under_1pct(self, report):
        assert report.model_error_pct < 1.0

    def test_modeled_drain_matches_pipeline_formula(self, report):
        expected = report.pipe_latency_cycles + (report.n_tokens - 1) * report.bottleneck_ii
        assert report.modeled_drain_cycles == pytest.approx(expected)


class TestStaticVsMeasuredBottleneck:
    """The finding: the topology-blind Mapper picks a different bottleneck."""

    def test_static_mapper_bottleneck_differs_from_measured(self, report):
        arch = elaborate(str(FIXTURES / CHIP))
        ops = load_ops(str(FIXTURES / TRACE))
        plan = estimate_plan(ops, arch, strict=False)
        # Mapper routes 6 matmuls to mac → calls mac busiest.
        assert plan.bottleneck_module == "mac"
        # But the real streamed-pipeline bottleneck is avp.
        assert report.bottleneck_module == "avp"
        assert plan.bottleneck_module != report.bottleneck_module


class TestRenderAndCLI:
    def test_render_has_bottleneck_and_stage_table(self, report):
        md = render_pipeline_bottleneck(report, arch_name="chip")
        assert "Pipeline bottleneck" in md
        assert "Per-stage service time" in md
        assert "bottleneck" in md
        assert "`avp`" in md

    def test_cli_bottleneck(self):
        import io
        buf = io.StringIO()
        rc = cli_main(["bottleneck", str(FIXTURES / CHIP)], out=buf)
        assert rc == 0
        s = buf.getvalue()
        assert "model error" in s
        assert "II=512" in s


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
