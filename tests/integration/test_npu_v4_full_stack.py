"""Step-8: NPU v4 full-stack — 26 hardware modules across 6 spec families.

Verifies SPEC-005 + 007 + 008 + 009 + 010 + 011 coexist in one elaborated
arch and the variant's stacked SPEC-011 knobs compose without overlap.
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
        str(FIXTURES / "usecase_npu_v4_full_stack.yaml"), max_cycles=5000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_npu_v4_loaded.yaml"), max_cycles=5000
    )
    return compare(base, var)


class TestFullStackElaborates:
    def test_26_modules_instantiate(self):
        arch = elaborate(str(FIXTURES / "usecase_npu_v4_full_stack.yaml"))
        # 7 SPEC-005 + 2 SPEC-007 + 4 SPEC-008 + 5 SPEC-009 + 2 SPEC-010 +
        # 6 SPEC-011 = 26.
        assert len(arch.modules) == 26

    def test_one_module_per_spec_family(self):
        arch = elaborate(str(FIXTURES / "usecase_npu_v4_full_stack.yaml"))
        for mid in ("mac", "mcu", "wb", "im2col", "pmu", "mc", "l2", "tlu"):
            assert mid in arch.modules

    def test_both_runs_valid(self, report):
        assert report.both_valid


class TestStackedSixSpecLevers:
    def test_aggregate_area_matches_per_section_sum(self, report):
        """
        Expected deltas (L2 now on the SPEC-013 physical SRAM macro model):
          MC banks 8 → 16              : +64_000    ([calibration knob])
          L2 cap 512 → 2048 KB         : +4_493_897 (SPEC-013 SRAM macro)
          SE structured                : +8_000     ([calibration knob])
          TLU table 2048 → 8192 + scatter: (SPEC-013 eDRAM table)
          CMDQ priority                : (SPEC-013 register file)
          MMU tlb 64 → 256             : +10_971    (SPEC-013 TLB CAM)
          Total                        : +9_399_526 μm²
        L2 (SRAM macro), TLU (eDRAM table), MMU (TLB CAM) and CMDQ (register
        file) are now on the physical model; MC/SE remain calibration knobs.
        """
        assert report.area_delta_um2 == pytest.approx(9_399_526, abs=3000)


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
