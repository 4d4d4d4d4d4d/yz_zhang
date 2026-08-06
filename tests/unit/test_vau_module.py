"""Conformance tests for the VAU module. SPEC-005 §6.1/§6.2, SPEC-001 §6, SPEC-004 §7."""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.vau import VAU, VAUGoldenModel


def _default_config(**overrides) -> dict:
    cfg = {"lanes": 16, "support_max": True, "support_relu": True}
    cfg.update(overrides)
    return cfg


def _make_op(op_type="add", required_caps=("vector_add",), n=64) -> StaticOperation:
    return StaticOperation(
        _op_type=op_type,
        _required_capabilities=required_caps,
        _shape_info=(("n_elements", n),),
        _precision=Precision(kind=PrecisionKind.FP32),
    )


class TestVAUClassMetadata:
    """SPEC-001 §6 class-level conformance."""

    def test_module_type(self):
        assert VAU.module_type() == "VAU"

    def test_module_version_is_semver(self):
        parts = VAU.module_version().split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(VAU.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), VAU.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"lanes": 999}, VAU.config_schema())

    def test_required_fields_enforced(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"support_relu": True}, VAU.config_schema())

    def test_capability_dependencies_consistent(self):
        names = {c.name for c in VAU.declared_capabilities()}
        for c in VAU.declared_capabilities():
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in VAU.port_specs()]
        assert len(names) == len(set(names))


class TestVAURegistry:

    def test_registered(self):
        assert "VAU" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        assert isinstance(ModuleRegistry.create("VAU", _default_config()), VAU)


class TestVAULifecycle:

    def test_default_activates_all(self):
        m = VAU()
        m.configure(_default_config())
        assert set(m.active_capabilities()) == {"vector_add", "vector_mul", "vector_max", "relu"}

    def test_disabling_flags_drops_optional(self):
        m = VAU()
        m.configure(_default_config(support_max=False, support_relu=False))
        assert set(m.active_capabilities()) == {"vector_add", "vector_mul"}

    def test_configure_only_once(self):
        m = VAU()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())

    def test_ports_exposed_after_configure(self):
        m = VAU()
        m.configure(_default_config())
        assert set(m.input_ports()) == {"in_a", "in_b", "in_cmd"}
        assert set(m.output_ports()) == {"out"}


class TestVAUCapabilityQueries:

    def _configured(self) -> VAU:
        m = VAU()
        m.configure(_default_config())
        return m

    def test_can_execute_consistency(self):
        m = self._configured()
        op = _make_op()
        assert m.can_execute(op) == set(op.required_capabilities).issubset(
            set(m.active_capabilities())
        )

    def test_can_execute_rejects_missing_capability(self):
        assert not self._configured().can_execute(_make_op(required_caps=("nope",)))

    def test_estimate_latency_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_latency(op) == m.estimate_latency(op)

    def test_more_lanes_is_faster(self):
        slow = VAU(); slow.configure(_default_config(lanes=4))
        fast = VAU(); fast.configure(_default_config(lanes=32))
        op = _make_op(n=128)
        assert fast.estimate_latency(op).min_cycles < slow.estimate_latency(op).min_cycles

    def test_estimate_energy_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_energy(op) == m.estimate_energy(op)


class TestVAUAreaPower:
    """SPEC-013 physical model: area = lanes × per-lane FP-ALU gates × cell area."""

    def test_area_matches_physical_model(self):
        from npu_sim import physical
        m = VAU()
        m.configure(_default_config())
        expected = physical.vau_area_um2(16, m.active_capabilities())
        assert m.total_area_um2() == pytest.approx(expected)
        assert expected > 0

    def test_area_scales_with_lanes(self):
        small = VAU(); small.configure(_default_config(lanes=16))
        big = VAU(); big.configure(_default_config(lanes=32))
        assert big.total_area_um2() == pytest.approx(2 * small.total_area_um2())

    def test_dropping_optional_reduces_area(self):
        full = VAU(); full.configure(_default_config())
        lean = VAU(); lean.configure(_default_config(support_max=False, support_relu=False))
        assert lean.total_area_um2() < full.total_area_um2()

    def test_energy_is_horowitz_grounded(self):
        from npu_sim import physical
        from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
        m = VAU(); m.configure(_default_config())
        op = StaticOperation(
            _op_type="relu", _required_capabilities=("relu",),
            _shape_info=(("n_elements", 100),),
            _precision=Precision(kind=PrecisionKind.FP16),
        )
        e = m.estimate_energy(op)
        expected = 100 * physical.vau_energy_per_elem_pj(m.active_capabilities())
        assert e.dynamic_pj == pytest.approx(expected)


class TestVAUState:

    def test_snapshot_idle_initially(self):
        m = VAU()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False and s.current_op is None


class TestVAUNumericalModel:
    """SPEC-004 §7 conformance for the paired golden model."""

    def test_registered_and_paired(self):
        model = NumericalModelRegistry.create("VAU", "golden", _default_config())
        assert isinstance(model, VAUGoldenModel)
        assert VAUGoldenModel.for_module_type() == VAU.module_type()

    def test_supported_capabilities_subset_of_declared(self):
        declared = {c.name for c in VAU.declared_capabilities()}
        assert set(VAUGoldenModel.supported_capabilities()).issubset(declared)

    def test_add_is_elementwise(self):
        model = VAUGoldenModel()
        model.configure(_default_config())
        a = np.arange(4, dtype=np.float32)
        b = np.ones(4, dtype=np.float32)
        out = model.execute(
            _make_op("add"),
            {"in_a": Tensor(a, NumericDType.FP32, (4,)), "in_b": Tensor(b, NumericDType.FP32, (4,))},
        )
        np.testing.assert_array_equal(out["out"].data, a + b)

    def test_relu_is_unary(self):
        model = VAUGoldenModel()
        model.configure(_default_config())
        a = np.array([-1.0, 2.0, -3.0, 4.0], dtype=np.float32)
        out = model.execute(_make_op("relu"), {"in_a": Tensor(a, NumericDType.FP32, (4,))})
        np.testing.assert_array_equal(out["out"].data, np.maximum(a, 0))

    def test_missing_second_operand_degrades_to_identity(self):
        model = VAUGoldenModel()
        model.configure(_default_config())
        a = np.arange(4, dtype=np.float32)
        out = model.execute(_make_op("add"), {"in_a": Tensor(a, NumericDType.FP32, (4,))})
        np.testing.assert_array_equal(out["out"].data, a)

    def test_execute_does_not_mutate_inputs(self):
        model = VAUGoldenModel()
        model.configure(_default_config())
        a = np.array([-1.0, 2.0], dtype=np.float32)
        original = a.copy()
        model.execute(_make_op("relu"), {"in_a": Tensor(a, NumericDType.FP32, (2,))})
        np.testing.assert_array_equal(a, original)
