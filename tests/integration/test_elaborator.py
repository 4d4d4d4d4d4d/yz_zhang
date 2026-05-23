"""End-to-end Elaborator tests. Reference: SPEC-003 §5, §7."""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.core.errors import (
    InvalidMappingHintError,
    OverrideError,
    PortNotFoundError,
    UnknownModuleTypeError,
)
from npu_sim.interfaces.transport import CdcConnectionSpec, ConnectionSpec
import npu_sim.modules  # noqa: F401  ensures Dummy is registered


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture
def elaborator() -> ArchitectureElaborator:
    return ArchitectureElaborator()


class TestBaselineElaboration:

    def test_baseline_loads(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        assert arch.name == "Dummy baseline"
        assert set(arch.modules) == {"producer", "consumer"}
        assert len(arch.connections) == 1
        assert set(arch.clocks) == {"main_clk"}

    def test_baseline_modules_are_configured(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        producer = arch.modules["producer"]
        # Configured with support_extra=true → both capabilities active.
        assert set(producer.active_capabilities()) == {"passthrough", "extra"}
        consumer = arch.modules["consumer"]
        assert consumer.active_capabilities() == ["passthrough"]

    def test_baseline_no_warnings(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        assert arch.warnings == []

    def test_topology_preserved(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        assert arch.topology is not None
        assert arch.topology.type == "single_die"
        assert arch.topology.dies[0]["id"] == "die_0"


class TestVariants:

    def test_throughput_variant(self, elaborator):
        baseline = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        variant = elaborator.elaborate(str(FIXTURES / "variant_throughput_half.yaml"))
        # The producer config changed; consumer config didn't.
        # We can verify the module instance by area: support_extra is unchanged
        # so total_area_um2 is the same here. Instead, check via internal field.
        assert variant.modules["producer"]._throughput == 1
        assert baseline.modules["producer"]._throughput == 2
        # consumer untouched
        assert variant.modules["consumer"]._throughput == baseline.modules["consumer"]._throughput

    def test_remove_consumer_prunes_connection(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "variant_remove_consumer.yaml"))
        assert set(arch.modules) == {"producer"}
        assert arch.connections == []
        # The merger should have produced a warning surfaced on the architecture.
        assert any("auto-pruned" in w for w in arch.warnings)

    def test_fusion(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "variant_fusion.yaml"))
        assert set(arch.modules) == {"fused"}
        assert arch.connections == []  # both endpoints removed; connection auto-pruned
        assert arch.modules["fused"]._throughput == 4


class TestChainInheritance:

    def test_chain_rejected(self, elaborator):
        with pytest.raises(OverrideError, match="Chain inheritance"):
            elaborator.elaborate(str(FIXTURES / "variant_chain_final.yaml"))


class TestErrors:

    def test_unknown_module_type_rejected(self, elaborator):
        with pytest.raises(UnknownModuleTypeError):
            elaborator.elaborate(str(FIXTURES / "bad_unknown_type.yaml"))

    def test_unknown_port_rejected(self, elaborator):
        with pytest.raises(PortNotFoundError, match="not declared"):
            elaborator.elaborate(str(FIXTURES / "bad_port_not_found.yaml"))

    def test_wrong_direction_rejected(self, elaborator):
        with pytest.raises(PortNotFoundError, match="OUTPUT"):
            elaborator.elaborate(str(FIXTURES / "bad_wrong_direction.yaml"))

    def test_unknown_mapping_hint_module_rejected(self, elaborator):
        with pytest.raises(InvalidMappingHintError, match="ghost_module"):
            elaborator.elaborate(str(FIXTURES / "bad_hints_unknown_module.yaml"))


class TestCrossDomain:
    """SPEC-002 §5.1 CDC detection at the Elaborator layer."""

    def test_cross_domain_connection_marked_cdc(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "multi_clock.yaml"))
        assert len(arch.connections) == 1
        conn = arch.connections[0]
        assert conn.is_cross_domain is True
        assert isinstance(conn.spec, CdcConnectionSpec)
        assert conn.spec.source_domain == "main_clk"
        assert conn.spec.sink_domain == "slow_clk"

    def test_same_domain_connection_is_plain(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        conn = arch.connections[0]
        assert conn.is_cross_domain is False
        assert isinstance(conn.spec, ConnectionSpec)
        assert not isinstance(conn.spec, CdcConnectionSpec)


class TestMappingHintsAccepted:

    def test_valid_hints_pass_through(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "variant_with_hints.yaml"))
        assert arch.mapping_hints == {
            "passthrough": {"stage_1": "producer", "stage_2": ["producer", "consumer"]}
        }


class TestConstraintWarnings:

    def test_constraint_violation_becomes_warning(self, elaborator):
        arch = elaborator.elaborate(str(FIXTURES / "bad_constraint_exceeded.yaml"))
        assert any("Constraint violated" in w for w in arch.warnings)
        # Elaboration itself does not fail.
        assert "a" in arch.modules


class TestConsistencyRules:
    """Phase 3.5 R6#9: custom cross-module consistency warnings."""

    def test_consistency_rule_warning_surfaced(self):
        def rule(merged: dict):
            # An artificial rule for the test: warn if any Dummy has support_extra=False.
            for m in merged.get("modules", []):
                if m.get("type") == "Dummy" and not m.get("config", {}).get("support_extra", False):
                    return f"module {m['id']!r} disables 'extra' capability"
            return None

        e = ArchitectureElaborator(consistency_rules=[rule])
        arch = e.elaborate(str(FIXTURES / "baseline_dummy.yaml"))
        # consumer has support_extra=False → expect the warning
        assert any("'consumer'" in w for w in arch.warnings)
