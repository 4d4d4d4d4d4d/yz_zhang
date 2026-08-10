"""Characterization of the area model's sensitivity — a known v1.1 gap.

Finding: `total_area_um2` sums each *active capability's* fixed
`area_cost_um2` (SPEC-001 §3.1 aggregation). Area therefore responds to
capability **presence** (toggling support_fp16, enable_double_buffer, …) but
is **blind to capability size** — scaling the MAC array 4×, doubling VAU
lanes, widening AVP's vector width all leave total area unchanged. Real
silicon area scales with the datapath size, so this is a fidelity gap: the
"A" axis of PPA is currently non-functional for sizing decisions.

Per CLAUDE.md the area coefficients are pre-silicon estimates awaiting Phase
5 calibration, so this is filed (docs/specs/README.md), NOT silently patched.

These tests are a **tripwire**: they assert the *current* size-blind
behavior. When Phase 5 gives the area model size terms, the
`TestScalingParamsDoNotChangeArea` assertions will start failing — that
failure is the signal to update this file, not a regression. The
`TestCapabilityTogglesChangeArea` cases document the half that already works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import sweep_config
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"


def _areas(module: str, key: str, values):
    """Areas measured across a config sweep of one knob (reuses sweep_config)."""
    rep = sweep_config(str(FIXTURES / CHIP), module, key, values)
    return [p.total_area_um2 for p in rep.points]


class TestMigratedModulesAreSizeAware:
    """Modules migrated to the physical model (SPEC-013): area scales."""

    def test_mac_array_rows_area_now_scales(self):
        # Doubling the array rows must increase area (∝ PE count).
        areas = _areas("mac", "array_rows", [32, 64])
        assert len(set(areas)) == 2, f"MAC area should scale with rows, got {areas}"
        assert areas[1] > areas[0]

    def test_vau_lanes_area_now_scales(self):
        # Doubling the lanes must increase area (∝ lane count).
        areas = _areas("vau", "lanes", [16, 32])
        assert len(set(areas)) == 2, f"VAU area should scale with lanes, got {areas}"
        assert areas[1] > areas[0]

    def test_dsb_buffer_kb_area_now_scales(self):
        # Doubling the SRAM buffer must increase area (∝ bytes).
        areas = _areas("dsb", "buffer_kb", [32, 64])
        assert len(set(areas)) == 2, f"DSB area should scale with buffer_kb, got {areas}"
        assert areas[1] > areas[0]


class TestScalingParamsDoNotChangeArea:
    """KNOWN GAP: remaining modules' size knobs leave area unchanged.

    Tripwire — as each module migrates to the physical model (SPEC-013 §5),
    move it out of this group (like MAC / VAU / DSB above).
    """

    def test_avp_vector_width_area_flat(self):
        areas = _areas("avp", "vector_width", [16, 32, 64])
        assert len(set(areas)) == 1


class TestCapabilityTogglesChangeArea:
    """The working half: area tracks which capabilities are active."""

    def test_mac_fp16_capability_adds_area(self):
        areas = _areas("mac", "support_fp16", [False, True])
        assert areas[1] > areas[0], "enabling fp16 should add capability area"

    def test_dsb_double_buffer_toggle_changes_area(self):
        areas = _areas("dsb", "enable_double_buffer", [True, False])
        assert len(set(areas)) == 2, "double-buffer presence should move area"


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
