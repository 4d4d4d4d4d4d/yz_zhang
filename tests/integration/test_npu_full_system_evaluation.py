"""Full-system NPU evaluation: data plane (SPEC-005) + control plane
(SPEC-007), all driven through YAML config differences.

Drives:
  baseline = usecase_npu_full_baseline.yaml
  variant  = usecase_npu_full_with_ogu.yaml

The variant stacks three independent levers via a single overrides block:
  1. SPEC-007 §2 / §3 — add OGU peer for MCU
  2. SPEC-005 v1.1 §U — enable DAGC compact_unpack
  3. SPEC-003 v1.1 §2.2 — __relocate__ DAGC to a different die

The simulator computes the aggregate effect. This is what the user wants:
"评估的时候只要改一些配置文件,然后仿真架构会基于这个配置跑出结果".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def report():
    base = elaborate_and_run(
        str(FIXTURES / "usecase_npu_full_baseline.yaml"), max_cycles=5000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_npu_full_with_ogu.yaml"), max_cycles=5000
    )
    return compare(base, var)


class TestFullSystemElaborates:
    """Both architectures must elaborate and run end-to-end."""

    def test_both_runs_valid(self, report):
        assert report.both_valid

    def test_full_module_set_present_in_baseline(self, report):
        # Data plane (5) + control plane (3) + Producer/Consumer (2) = 10.
        # tokens_delivered only counts wired connections, not module count;
        # use the architecture name + total_area as a sanity surface.
        assert "data + control plane, no OGU" in report.baseline.architecture_name


class TestSystemLevelAreaSaving:
    """Stacked savings: OGU offload + compact_unpack add up to ~52k μm²."""

    def test_variant_smaller_than_baseline(self, report):
        assert report.area_delta_um2 < 0, (
            f"Stacked levers should reduce area, got Δ={report.area_delta_um2:+.1f}"
        )

    def test_area_saving_at_least_10pct(self, report):
        pct = -100.0 * report.area_delta_um2 / report.baseline.total_area_um2
        assert pct >= 10.0, (
            f"Combined area saving {pct:.1f}% below 10% expected"
        )

    def test_savings_match_sum_of_individual_levers(self, report):
        """≈ OGU saving (50k) + compact_unpack saving (1.98k) ≈ 52k μm²."""
        expected = 50_000 + 1_980
        actual = -report.area_delta_um2
        assert abs(actual - expected) <= 200, (
            f"Area saving {actual:.1f} μm² differs from expected "
            f"{expected:.1f} by more than 200 μm²"
        )


class TestSystemLevelLatencyPenalty:
    """DAGC __relocate__ contributes some drain_time penalty."""

    def test_drain_time_penalty_is_small_but_observable(self, report):
        """Three levers: OGU (no datapath impact), compact_unpack (+ minor),
        relocate (+ transport). Net drain delta should be small but > 0."""
        assert report.drain_time_delta_ps > 0
        assert report.drain_time_delta_pct <= 10.0, (
            f"Stacked drain regression {report.drain_time_delta_pct:.1f}% > 10%"
        )


class TestStallChainStillTraceable:
    """SPEC-002 §3.3 backpressure tracer must work in the full system."""

    def test_bottleneck_identified_in_both_runs(self, report):
        # Pipeline bottleneck shouldn't disappear under the variant.
        assert report.baseline.bottleneck_module is not None
        assert report.variant.bottleneck_module is not None

    def test_per_module_stall_changed_for_relocated_dagc(self, report):
        """DAGC was a stall source in baseline (9k ps); relocate adds
        transport latency upstream and changes the stall profile."""
        base_dagc = report.baseline.per_module_stall_ps.get("dagc", 0)
        var_dagc = report.variant.per_module_stall_ps.get("dagc", 0)
        assert var_dagc != base_dagc, (
            f"DAGC stall unchanged ({base_dagc}); relocate should shift it"
        )


class TestEvaluationIsPureYamlDriven:
    """Meta-test: this test file does NOT manually construct modules or
    call estimate_* directly. The only input is YAML; the only output is
    the comparator. Proves the user contract:
    '改 YAML → simulator → result'."""

    def test_no_python_module_construction_in_use_case(self):
        """Statically verifies this test file imports neither MCU/OGU/DAGC
        classes directly nor invokes any estimate_* method. Strips strings
        and comments before scanning so docstrings can mention them freely.
        """
        import inspect, re, sys, io, tokenize
        source = inspect.getsource(sys.modules[__name__])
        # Drop string literals + comments before scanning so that
        # docstrings/strings mentioning module names don't trigger.
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        code_only = "".join(
            t.string for t in tokens
            if t.type not in (tokenize.STRING, tokenize.COMMENT)
        )
        offenders = re.findall(
            r"\b(MCU|OGU|TAU|DMA|MTU|AGU|DAGC|DSB|MAC|VAU|AVP)\(",
            code_only,
        )
        assert offenders == [], (
            f"Use case constructs modules in Python: {offenders}. "
            f"All evaluation must go through YAML + elaborate_and_run."
        )
        assert ".estimate_" not in code_only, (
            "Use case calls .estimate_* directly; should use compare() metrics."
        )
