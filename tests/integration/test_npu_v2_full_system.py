"""SPEC-008 Step 5 — full-system NPU v2 evaluation, YAML-driven.

Combines SPEC-005 data plane (DAGC/DSB/MAC/VAU/AVP) + SPEC-007 control
plane (MCU/AGU) + SPEC-008 memory+precision plane (WB/OB/Quant/SFU) into
a single architecture. The variant flips four SPEC-008 knobs (WB
capacity + prefetch, OB tile/in-flight, Quant per-channel, SFU trig) in
one overrides block and the simulator computes the aggregate impact.
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
        str(FIXTURES / "usecase_npu_v2_baseline.yaml"), max_cycles=5000
    )
    var = elaborate_and_run(
        str(FIXTURES / "usecase_npu_v2_loaded.yaml"), max_cycles=5000
    )
    return compare(base, var)


class TestFullSystemElaborates:
    def test_both_runs_valid(self, report):
        assert report.both_valid

    def test_all_module_classes_present_in_baseline_arch(self):
        from npu_sim.architecture.elaborator import ArchitectureElaborator
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
        from npu_sim.evaluation import elaborate
        arch = elaborate(str(FIXTURES / "usecase_npu_v2_baseline.yaml"))
        ids = set(arch.modules.keys())
        # SPEC-005 + SPEC-007 + SPEC-008 modules all in.
        required = {
            "prod", "dagc", "dsb", "mac", "vau", "avp", "cons",   # data plane
            "mcu_0", "agu_mac",                                    # control
            "wb", "ob", "q_act", "sfu",                            # memory/precision
        }
        assert required.issubset(ids), (
            f"missing modules: {required - ids}"
        )


class TestStackedSPEC008Levers:
    """Four SPEC-008 knobs flip together — aggregate area matches per-§ sum."""

    def test_aggregate_area_matches_per_section_sum(self, report):
        """
        Per-section area deltas expected:
          §1 WB cap 64→256 KB        : (256-64) × 1200 = +230_400
          §1 WB enable_prefetch       :                = +4_000
          §2 OB tile 8→32 + 1→2       : 32×2 - 8×1 = 56 × 1500 = +84_000
          §3 Quant per_channel        : 4000-500       = +3_500
          §4 SFU enable_trig          : 4000+4000      = +8_000
          Total                                       = +329_900
        """
        assert report.area_delta_um2 == pytest.approx(329_900, abs=1.0)

    def test_static_power_grows_with_storage(self, report):
        """WB capacity_kb × 0.5 μW/KB + capability extras."""
        # 192 KB × 0.5 = 96 μW from WB capacity alone, plus minor cap extras.
        assert report.static_power_delta_uw > 90.0

    def test_drain_time_within_small_band(self, report):
        """Quant per_channel adds 1 cycle/token; on a tiny workload that's
        small. Bottleneck shouldn't shift."""
        assert abs(report.drain_time_delta_pct) <= 20.0, (
            f"drain_time_delta_pct = {report.drain_time_delta_pct:.1f}%"
        )


class TestSPEC008ModulesInstantiate:
    """All SPEC-008 modules elaborate in the full-system arch without errors."""

    def test_all_modules_active(self):
        from npu_sim.evaluation import elaborate
        arch = elaborate(str(FIXTURES / "usecase_npu_v2_baseline.yaml"))
        for mid, expected_cap in [
            ("wb", "weight_storage"),
            ("ob", "psum_accumulate"),
            ("q_act", "fp32_to_int8"),
            ("sfu", "exp"),
        ]:
            caps = set(arch.modules[mid].active_capabilities())
            assert expected_cap in caps, (
                f"{mid!r}: expected capability {expected_cap!r} missing"
            )

    def test_waveform_renders_data_plane_stages(self):
        """Data plane modules are wired and active — their stages should
        appear in the waveform. (Wiring WB/OB/Quant/SFU into the existing
        datapath without breaking SPEC-005 contracts is left to a future
        full integration commit.)"""
        from npu_sim.evaluation import elaborate
        from npu_sim.evaluation.runner import run_simulation
        from npu_sim.reporting.waveform import WaveformRecorder

        arch = elaborate(str(FIXTURES / "usecase_npu_v2_baseline.yaml"))
        rec = WaveformRecorder()
        run_simulation(arch, max_cycles=500, per_cycle_hook=rec)
        rendered = rec.render(arch, max_cycles=300)
        # Data plane stage glyphs.
        for stage in ("unpack_bfp", "stage_tile", "writeback_psum"):
            assert stage in rendered, (
                f"data-plane stage {stage!r} missing from waveform"
            )


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
