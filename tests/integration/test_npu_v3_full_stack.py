"""Step-7: full-stack NPU v3 integration — 19 modules across 5 specs.

The single comprehensive YAML-driven test that proves SPEC-005 + 007 +
008 + 009 + 010 coexist and their area models compose without overlap.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
import npu_sim.modules  # noqa: F401
from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def report():
    base = elaborate_and_run(
        str(FIXTURES / "usecase_npu_v3_full_stack.yaml"), max_cycles=5000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_npu_v3_loaded.yaml"), max_cycles=5000
    )
    return compare(base, var)


class TestFullStackElaborates:
    def test_20_modules_instantiate(self):
        arch = elaborate(str(FIXTURES / "usecase_npu_v3_full_stack.yaml"))
        # 7 SPEC-005 (prod/dagc/dsb/mac/vau/avp/cons) + 2 SPEC-007 (mcu/agu)
        # + 4 SPEC-008 (wb/ob/q_act/sfu) + 5 SPEC-009 (im2col/rdc/noc/cde/tr)
        # + 2 SPEC-010 (pmu/sync) = 20.
        assert len(arch.modules) == 20

    def test_one_module_per_spec_family(self):
        arch = elaborate(str(FIXTURES / "usecase_npu_v3_full_stack.yaml"))
        # Pick one representative module per spec family and confirm presence.
        for mid in ["mac", "mcu", "wb", "im2col", "pmu"]:
            assert mid in arch.modules

    def test_both_runs_valid(self, report):
        assert report.both_valid


class TestStackedFiveSpecLevers:
    """Area delta = sum of per-spec contributions, no overlap."""

    def test_aggregate_area_matches_per_section_sum(self, report):
        """
        Expected breakdown:
          §008 WB cap 64→256 KB    : 192 × 1200 = +230_400
          §009 IM2COL 1×1→3×3      : kernel size doesn't affect area = 0
          §009 RDC tree_width 8→16 : (16-8)/8 × 12_000 = +12_000
          §010 PMU 3→8 counters    : 5 × 5_000 = +25_000
          §010 SYNC 2→8 participants: 6 × 1_500 = +9_000
          Total                                = +276_400
        """
        assert report.area_delta_um2 == pytest.approx(276_400, abs=200)

    def test_drain_time_within_small_band(self, report):
        """Variant flips knobs that don't affect main pipeline → drain stable."""
        assert abs(report.drain_time_delta_pct) < 10.0 or report.drain_time_delta_ps == 0


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
