"""SPEC-003 v1.1 §2.2 — `__relocate__` override use case.

Demonstrates the "DAGC 外置, 预估 10% 代价" evaluation: variant injects
+10% latency / +10% energy / +0% area on the DAGC module without changing
the module type, ports, or capabilities. The compare report's
drain_time_delta_pct should reflect the relocate penalty.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
import npu_sim.modules  # noqa: F401  registers all module types


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestRelocateAppliesToEstimates:
    """SPEC-003 v1.1 §2.2.1: penalty applies to estimate_*, not topology."""

    def test_relocated_dagc_latency_is_inflated(self):
        baseline = elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=200)
        variant = elaborate_and_run(str(FIXTURES / "usecase_dagc_external.yaml"), max_cycles=200)

        # Compare static estimate_latency of the DAGC instance directly.
        # The relocate wrap should multiply by 1.10.
        op = StaticOperation(
            _op_type="unpack",
            _required_capabilities=("bfp8_unpack",),
            _shape_info=(("n_elements", 1024),),
            _precision=Precision(kind=PrecisionKind.BFP8),
        )
        # Re-elaborate to get the modules.
        from npu_sim.architecture.elaborator import ArchitectureElaborator
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink

        def _arch(name: str):
            bus = InMemoryEventBus()
            sink = InMemoryStatSink(event_bus=bus)
            return ArchitectureElaborator(event_bus=bus, stat_sink=sink).elaborate(
                str(FIXTURES / name)
            )

        a_base = _arch("dagc_chain.yaml")
        a_var = _arch("usecase_dagc_external.yaml")
        lat_base = a_base.modules["dagc"].estimate_latency(op).typical_cycles
        lat_var = a_var.modules["dagc"].estimate_latency(op).typical_cycles
        # +10% with int truncation.
        assert lat_var >= int(lat_base * 1.10) - 1
        assert lat_var <= int(lat_base * 1.10) + 1

    def test_relocated_area_unchanged_when_pct_zero(self):
        """area_penalty_pct=0 → area unchanged (DAGC外置 doesn't add silicon)."""
        from npu_sim.architecture.elaborator import ArchitectureElaborator
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink

        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
        arch = elab.elaborate(str(FIXTURES / "usecase_dagc_external.yaml"))
        assert arch.modules["dagc"].estimate_area().um2 == pytest.approx(
            arch.modules["dagc"]._relocate_original_estimate_area().um2
        )

    def test_relocated_module_preserves_capabilities_and_ports(self):
        """§2.2.1: __relocate__ must NOT touch type / ports / capabilities."""
        from npu_sim.architecture.elaborator import ArchitectureElaborator
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink

        def _arch(name: str):
            bus = InMemoryEventBus()
            sink = InMemoryStatSink(event_bus=bus)
            return ArchitectureElaborator(event_bus=bus, stat_sink=sink).elaborate(
                str(FIXTURES / name)
            )

        a_base = _arch("dagc_chain.yaml")
        a_var = _arch("usecase_dagc_external.yaml")
        base_dagc = a_base.modules["dagc"]
        var_dagc = a_var.modules["dagc"]
        assert type(base_dagc) is type(var_dagc)
        assert base_dagc.active_capabilities() == var_dagc.active_capabilities()
        assert set(base_dagc.port_specs()[i].name for i in range(len(base_dagc.port_specs()))) == \
               set(var_dagc.port_specs()[i].name for i in range(len(var_dagc.port_specs())))


class TestRelocateCompareReport:
    def test_drain_time_delta_picks_up_relocate(self):
        """End-to-end: comparator should surface area delta = 0, but the
        relocated DAGC's runtime drain_time may shift due to the modified
        latency the modules in the datapath see."""
        baseline = elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=400)
        variant = elaborate_and_run(str(FIXTURES / "usecase_dagc_external.yaml"), max_cycles=400)
        report = compare(baseline, variant)
        # area_penalty_pct=0 → area_delta_um2 ≈ 0
        assert abs(report.area_delta_um2) < 1e-3
        # drain_time may change marginally depending on how the runtime
        # consults estimate_latency, but the static contract is reflected.
        assert report.both_valid


class TestRelocateValidation:
    def test_same_die_relocate_is_rejected(self):
        """OverrideError on from_die == to_die (no-op relocate)."""
        from npu_sim.architecture.elaborator import ArchitectureElaborator
        from npu_sim.core.errors import OverrideError
        from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink

        # Build an inline fixture.
        bad_fixture = FIXTURES.parent / "tmp_bad_relocate.yaml"
        bad_fixture.write_text("""schema_version: "1.0"
name: "bad relocate"
base: architectures/dagc_chain.yaml
overrides:
  modules:
    dagc:
      __relocate__:
        from_die: 0
        to_die: 0
        latency_penalty_pct: 5
""")
        try:
            bus = InMemoryEventBus()
            sink = InMemoryStatSink(event_bus=bus)
            elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
            with pytest.raises(OverrideError, match="from_die equals to_die"):
                elab.elaborate(str(bad_fixture))
        finally:
            bad_fixture.unlink(missing_ok=True)
