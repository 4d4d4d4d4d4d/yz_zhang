"""Machine-checks for docs/Fidelity-Audit.md — pin what's real vs placeholder.

The audit's claims are testable, so they're tested here to stop silent drift:

  * POSITIVE — the mechanism is a real simulation: per-token timing is derived
    from config + data flow, so changing a config knob changes the measured
    drain, and the datapath's per-stage service times are non-uniform (each is
    computed, not one global constant).

  * DISCLOSURE — the `[calibration knob]` provenance marker is present in the
    SPEC-007/011 modules' source but currently ABSENT from the SPEC-005 compute
    modules. The absence assertions are a tripwire: when the markers are added
    (finding #5), update this test.

No hardware modules are constructed and no estimate_* is called (provenance is
checked at the source-text level), so this stays a read-only meta-test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import analyze_pipeline_bottleneck, elaborate, sweep_config
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"
MODULES = Path(__file__).parent.parent.parent / "npu_sim" / "modules"


class TestTimingIsRealSimulation:
    """The mechanism is genuine: timing emerges from architecture, not lookup."""

    def test_drain_responds_to_a_config_knob(self):
        # If timing were an arbitrary constant, changing throughput wouldn't
        # move drain. It does → timing is derived from config.
        rep = sweep_config(str(FIXTURES / CHIP), "dsb", "read_throughput", [4, 8])
        drains = [p.drain_cycles for p in rep.points]
        assert drains[0] != drains[1]
        assert drains[1] < drains[0]  # more read bandwidth → faster

    def test_per_stage_service_times_are_non_uniform(self):
        # Each stage's II is computed from its own config + token size; they are
        # not all the same magic number.
        rep = analyze_pipeline_bottleneck(elaborate(str(FIXTURES / CHIP)))
        iis = {round(s.service_ii) for s in rep.stages}
        assert len(iis) > 1, f"expected varied per-stage II, got {iis}"

    def test_bottleneck_model_reconciles_measured(self):
        # The 0.1% reconciliation is emergent, not fitted — the headline
        # evidence that this is a real simulation.
        rep = analyze_pipeline_bottleneck(elaborate(str(FIXTURES / CHIP)))
        assert rep.model_error_pct < 1.0


class TestCoefficientProvenanceDisclosure:
    """Where the '[calibration knob]' honesty marker is — and isn't (yet)."""

    def _src(self, *parts: str) -> str:
        return (MODULES.joinpath(*parts)).read_text(encoding="utf-8")

    def test_dram_and_control_modules_carry_the_marker(self):
        assert "[calibration knob]" in self._src("dram", "l2_module.py")
        assert "[calibration knob]" in self._src("control", "mcu_module.py")

    def test_migrated_modules_are_physically_grounded(self):
        # MAC, VAU, DSB and AVP cite a literature-derived physical basis
        # (SPEC-013) instead of placeholder constants.
        for area, mod in [("mac", "mac_module.py"), ("vau", "vau_module.py"),
                          ("dsb", "dsb_module.py"), ("avp", "avp_module.py")]:
            src = self._src(area, mod)
            assert "physical" in src and "SPEC-013" in src

    def test_remaining_compute_modules_still_lack_grounding(self):
        # Tripwire: DAGC is the last compute module not yet migrated
        # (SPEC-013 §5 rollout). When grounded, move it above.
        src = self._src("dagc", "dagc_module.py")
        assert "SPEC-013" not in src, (
            "dagc_module.py now references SPEC-013 — move it to the grounded test"
        )


def test_audit_doc_exists():
    doc = Path(__file__).parent.parent.parent / "docs" / "Fidelity-Audit.md"
    assert doc.exists() and "信任矩阵" in doc.read_text(encoding="utf-8")
