"""Conformance tests for the DSB module. SPEC-005 §6.1/§6.2, SPEC-001 §6, SPEC-004 §7."""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.dsb import DSB, DSBGoldenModel


def _default_config(**overrides) -> dict:
    cfg = {
        "buffer_kb": 64,
        "n_banks": 2,
        "read_throughput": 4,
        "enable_double_buffer": True,
        "broadcast_factor": 1,
    }
    cfg.update(overrides)
    return cfg


def _make_op(required_caps=("tile_buffer",), n: int = 64) -> StaticOperation:
    return StaticOperation(
        _op_type="stage",
        _required_capabilities=required_caps,
        _shape_info=(("n_elements", n),),
        _precision=Precision(kind=PrecisionKind.FP32),
    )


class TestDSBClassMetadata:
    """SPEC-001 §6 class-level conformance."""

    def test_module_type(self):
        assert DSB.module_type() == "DSB"

    def test_module_version_is_semver(self):
        parts = DSB.module_version().split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(DSB.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), DSB.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"buffer_kb": 9999}, DSB.config_schema())

    def test_required_fields_enforced(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"n_banks": 2}, DSB.config_schema())

    def test_capability_dependencies_consistent(self):
        names = {c.name for c in DSB.declared_capabilities()}
        for c in DSB.declared_capabilities():
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in DSB.port_specs()]
        assert len(names) == len(set(names))


class TestDSBRegistry:

    def test_registered(self):
        assert "DSB" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        assert isinstance(ModuleRegistry.create("DSB", _default_config()), DSB)


class TestDSBLifecycle:

    def test_default_activates_buffer_and_double_buffer(self):
        m = DSB()
        m.configure(_default_config())
        assert set(m.active_capabilities()) == {"tile_buffer", "double_buffer"}

    def test_broadcast_capability_gated_by_factor(self):
        m = DSB()
        m.configure(_default_config(broadcast_factor=4))
        assert "broadcast" in m.active_capabilities()

    def test_disabling_double_buffer_drops_capability(self):
        m = DSB()
        m.configure(_default_config(enable_double_buffer=False))
        assert set(m.active_capabilities()) == {"tile_buffer"}

    def test_configure_only_once(self):
        m = DSB()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())

    def test_ports_exposed_after_configure(self):
        m = DSB()
        m.configure(_default_config())
        assert set(m.input_ports()) == {"in_data", "in_cmd"}
        assert set(m.output_ports()) == {"out_data"}


class TestDSBCapabilityQueries:

    def _configured(self) -> DSB:
        m = DSB()
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

    def test_higher_read_throughput_is_faster(self):
        slow = DSB(); slow.configure(_default_config(read_throughput=2))
        fast = DSB(); fast.configure(_default_config(read_throughput=8))
        op = _make_op(n=128)
        assert fast.estimate_latency(op).min_cycles < slow.estimate_latency(op).min_cycles

    def test_estimate_energy_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_energy(op) == m.estimate_energy(op)


class TestDSBAreaPower:
    """SPEC-001 §3.1 area = sum over active capabilities."""

    def test_total_area_equals_active_sum(self):
        m = DSB()
        m.configure(_default_config())
        expected = sum(
            c.area_cost_um2 for c in DSB.declared_capabilities()
            if c.name in m.active_capabilities()
        )
        assert m.total_area_um2() == expected

    def test_dropping_double_buffer_reduces_area(self):
        full = DSB(); full.configure(_default_config())
        lean = DSB(); lean.configure(_default_config(enable_double_buffer=False))
        assert lean.total_area_um2() < full.total_area_um2()


class TestDSBState:

    def test_snapshot_idle_initially(self):
        m = DSB()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False and s.current_op is None


class TestDSBNumericalModel:
    """SPEC-004 §7 conformance for the paired golden model."""

    def test_registered_and_paired(self):
        model = NumericalModelRegistry.create("DSB", "golden", _default_config())
        assert isinstance(model, DSBGoldenModel)
        assert DSBGoldenModel.for_module_type() == DSB.module_type()

    def test_supported_capabilities_subset_of_declared(self):
        declared = {c.name for c in DSB.declared_capabilities()}
        assert set(DSBGoldenModel.supported_capabilities()).issubset(declared)

    def test_execute_is_identity_copy(self):
        model = DSBGoldenModel()
        model.configure(_default_config())
        arr = np.arange(8, dtype=np.float32)
        out = model.execute(_make_op(), {"in_data": Tensor(arr, NumericDType.FP32, (8,))})
        np.testing.assert_array_equal(out["in_data"].data, arr)

    def test_execute_does_not_mutate_inputs(self):
        model = DSBGoldenModel()
        model.configure(_default_config())
        arr = np.arange(8, dtype=np.float32)
        original = arr.copy()
        model.execute(_make_op(), {"in_data": Tensor(arr, NumericDType.FP32, (8,))})
        np.testing.assert_array_equal(arr, original)

    def test_broadcast_replicates_along_new_axis(self):
        model = DSBGoldenModel()
        model.configure(_default_config(broadcast_factor=3))
        arr = np.arange(4, dtype=np.float32)
        out = model.execute(_make_op(), {"in_data": Tensor(arr, NumericDType.FP32, (4,))})
        assert out["in_data"].data.shape == (3, 4)
        for i in range(3):
            np.testing.assert_array_equal(out["in_data"].data[i], arr)
