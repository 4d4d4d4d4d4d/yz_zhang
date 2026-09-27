"""Tests for ModuleRegistry. Reference: SPEC-001 §3.1.1, §4."""

from __future__ import annotations

import jsonschema
import pytest

from npu_sim.core.errors import (
    DuplicateModuleTypeError,
    InvalidModuleTypeNameError,
    UnknownModuleTypeError,
)
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import Capability, IModule, ModuleState
from npu_sim.interfaces.transport import DataType, PortDirection, PortSpec


def _make_module_class(
    type_name: str,
    *,
    schema: dict | None = None,
    caps: list[Capability] | None = None,
) -> type[IModule]:
    """Generate a minimal IModule subclass with the given type name."""

    schema = schema or {"type": "object", "properties": {}}
    caps = caps if caps is not None else []

    class _GeneratedModule(IModule):
        @classmethod
        def module_type(cls) -> str:
            return type_name

        @classmethod
        def module_version(cls) -> str:
            return "0.1.0"

        @classmethod
        def config_schema(cls) -> dict:
            return schema

        @classmethod
        def declared_capabilities(cls):
            return caps

        @classmethod
        def port_specs(cls):
            return []

        def bind_services(self, event_bus, stat_sink, clock):
            pass

        def configure(self, config):
            pass

        def reset(self):
            pass

        def destroy(self):
            pass

        def input_ports(self):
            return {}

        def output_ports(self):
            return {}

        def active_capabilities(self):
            return []

        def can_execute(self, operation):
            return True

        def estimate_latency(self, operation):
            raise NotImplementedError

        def estimate_energy(self, operation):
            raise NotImplementedError

        def snapshot_state(self):
            return ModuleState(busy=False)

    _GeneratedModule.__name__ = type_name
    return _GeneratedModule


class TestModuleTypeNaming:
    """SPEC-001 §3.1.1: PascalCase, no underscore, no leading digit, <= 24 chars."""

    @pytest.mark.parametrize(
        "name",
        ["DAGC", "MatVecArray", "DSB", "MtuFused", "A"],
    )
    def test_valid_names_accepted(self, name, isolated_registry):
        cls = _make_module_class(name)
        isolated_registry.register(cls)
        assert name in isolated_registry.list_modules()

    @pytest.mark.parametrize(
        "name",
        [
            "dagc",         # lowercase first letter
            "MAC_Array",    # contains underscore
            "MTU_Fused",    # the v0.1 residual to be fixed in v0.3
            "4BitReorder",  # leads with a digit
            "MAC-Array",    # contains hyphen
            "Mac Array",    # contains space
            "A" * 25,       # too long
            "",             # empty
        ],
    )
    def test_invalid_names_rejected(self, name, isolated_registry):
        cls = _make_module_class(name)
        with pytest.raises(InvalidModuleTypeNameError):
            isolated_registry.register(cls)


class TestRegistration:

    def test_duplicate_registration_rejected(self, isolated_registry):
        cls_a = _make_module_class("Alpha")
        cls_b = _make_module_class("Alpha")
        isolated_registry.register(cls_a)
        with pytest.raises(DuplicateModuleTypeError):
            isolated_registry.register(cls_b)

    def test_re_registration_of_same_class_ok(self, isolated_registry):
        """Idempotent register (same class twice) should succeed."""
        cls = _make_module_class("Beta")
        isolated_registry.register(cls)
        # Same class object again is fine.
        isolated_registry.register(cls)
        assert "Beta" in isolated_registry.list_modules()

    def test_invalid_config_schema_rejected(self, isolated_registry):
        cls = _make_module_class(
            "Gamma",
            schema={"type": "object", "properties": "this is not a dict"},
        )
        with pytest.raises(jsonschema.SchemaError):
            isolated_registry.register(cls)

    def test_capability_dependency_inconsistency_rejected(self, isolated_registry):
        bad_cap = Capability(
            name="x",
            description="",
            area_cost_um2=0,
            static_power_uw=0,
            dynamic_energy_pj=0,
            depends_on=("nonexistent",),
        )
        cls = _make_module_class("Delta", caps=[bad_cap])
        with pytest.raises(InvalidModuleTypeNameError, match="depends on"):
            isolated_registry.register(cls)

    def test_create_unknown_type_raises(self, isolated_registry):
        with pytest.raises(UnknownModuleTypeError):
            isolated_registry.create("NotRegistered", {})

    def test_create_validates_config(self, isolated_registry):
        cls = _make_module_class(
            "Epsilon",
            schema={
                "type": "object",
                "properties": {"x": {"type": "integer", "minimum": 0}},
                "required": ["x"],
            },
        )
        isolated_registry.register(cls)

        # Valid config: instantiates.
        inst = isolated_registry.create("Epsilon", {"x": 5})
        assert inst is not None

        # Invalid config: schema rejects.
        with pytest.raises(jsonschema.ValidationError):
            isolated_registry.create("Epsilon", {"x": -1})

        # Missing required field rejected.
        with pytest.raises(jsonschema.ValidationError):
            isolated_registry.create("Epsilon", {})
