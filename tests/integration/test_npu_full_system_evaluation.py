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

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


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

    def test_stacked_absolute_saving_is_about_52k(self, report):
        # The real invariant is the ABSOLUTE stacked saving (OGU offload +
        # compact_unpack ≈ 52k µm²). The old ">=10%" threshold was an artifact
        # of an unrealistically small (size-blind) MAC area; now that MAC area
        # is physically grounded (SPEC-013) the chip is MAC-dominated (~1.17M
        # µm²), so the same real saving is ~4.4% — small relative to the
        # compute array, which is the truth for a control-plane/unpack lever.
        assert report.area_delta_um2 <= -50_000, (
            f"Stacked saving {report.area_delta_um2:+.0f} µm² below ~52k expected"
        )

    def test_savings_decompose_into_ogu_plus_compact(self, report):
        """≈ OGU offload saving (~50k, capability-level) + compact_unpack
        staging-RF saving. compact_unpack is now modeled physically (SPEC-013:
        the saving scales with the unpack datapath), so it is larger than the
        old placeholder −1.98k constant. The OGU floor is unchanged."""
        actual = -report.area_delta_um2
        assert actual >= 50_000, "OGU-offload saving floor (~50k) not met"
        compact_saving = actual - 50_000
        # physical staging-RF reduction, ≥ the SPEC-005 §U.1 calibration floor
        assert compact_saving >= 1_500


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


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
