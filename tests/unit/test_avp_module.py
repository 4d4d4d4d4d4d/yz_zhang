"""Conformance tests for the AVP module. SPEC-005 §6.1/§6.2, SPEC-001 §6, SPEC-004 §7."""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.avp import AVP, AVPGoldenModel


def _default_config(**overrides) -> dict:
    cfg = {
        "vector_width": 16,
        "support_softmax": True,
        "support_layernorm": True,
        "support_pooling": False,
        "lut_entries": 256,
    }
    cfg.update(overrides)
    return cfg


def _make_op(op_type="gelu", required_caps=("gelu",), n=64) -> StaticOperation:
    return StaticOperation(
        _op_type=op_type,
        _required_capabilities=required_caps,
        _shape_info=(("n_elements", n),),
        _precision=Precision(kind=PrecisionKind.FP32),
    )


class TestAVPClassMetadata:
    """SPEC-001 §6 class-level conformance."""

    def test_module_type(self):
        assert AVP.module_type() == "AVP"

    def test_module_version_is_semver(self):
        parts = AVP.module_version().split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(AVP.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), AVP.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"vector_width": 999}, AVP.config_schema())

    def test_required_fields_enforced(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"support_softmax": True}, AVP.config_schema())

    def test_capability_dependencies_consistent(self):
        names = {c.name for c in AVP.declared_capabilities()}
        for c in AVP.declared_capabilities():
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in AVP.port_specs()]
        assert len(names) == len(set(names))


class TestAVPRegistry:

    def test_registered(self):
        assert "AVP" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        assert isinstance(ModuleRegistry.create("AVP", _default_config()), AVP)


class TestAVPLifecycle:

    def test_default_activates_gelu_softmax_layernorm(self):
        m = AVP()
        m.configure(_default_config())
        assert set(m.active_capabilities()) == {"gelu", "softmax", "layernorm"}

    def test_pooling_gated_by_flag(self):
        m = AVP()
        m.configure(_default_config(support_pooling=True))
        assert "pooling" in m.active_capabilities()

    def test_disabling_flags_drops_optional(self):
        m = AVP()
        m.configure(_default_config(support_softmax=False, support_layernorm=False))
        assert set(m.active_capabilities()) == {"gelu"}

    def test_configure_only_once(self):
        m = AVP()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())

    def test_ports_exposed_after_configure(self):
        m = AVP()
        m.configure(_default_config())
        assert set(m.input_ports()) == {"in_data", "in_cmd"}
        assert set(m.output_ports()) == {"out_data"}


class TestAVPCapabilityQueries:

    def _configured(self) -> AVP:
        m = AVP()
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

    def test_unsupported_op_zero_cycles(self):
        # pooling disabled by default -> op not active -> unsupported.
        m = self._configured()
        assert m.estimate_latency(_make_op("pooling", n=128)).min_cycles == 0

    def test_pooling_cheaper_than_gelu_per_element(self):
        m = AVP(); m.configure(_default_config(support_pooling=True))
        gelu = m.estimate_latency(_make_op("gelu", n=128))
        pool = m.estimate_latency(_make_op("pooling", required_caps=("pooling",), n=128))
        assert pool.min_cycles < gelu.min_cycles

    def test_estimate_energy_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_energy(op) == m.estimate_energy(op)


class TestAVPAreaPower:
    """SPEC-013 physical model: area = FP-ALU array (∝ vector_width) + LUT SRAM."""

    def test_area_matches_physical_model(self):
        from npu_sim import physical
        m = AVP()
        m.configure(_default_config())
        expected = physical.avp_area_um2(16, 256, m.active_capabilities())
        assert m.total_area_um2() == pytest.approx(expected)
        assert expected > 0

    def test_area_scales_with_vector_width(self):
        # Resolves the original finding: AVP area was insensitive to vector_width.
        small = AVP(); small.configure(_default_config(vector_width=16))
        big = AVP(); big.configure(_default_config(vector_width=32))
        assert big.total_area_um2() > small.total_area_um2()

    def test_area_grows_with_lut_entries(self):
        few = AVP(); few.configure(_default_config(lut_entries=256))
        many = AVP(); many.configure(_default_config(lut_entries=1024))
        assert many.total_area_um2() > few.total_area_um2()

    def test_dropping_optional_reduces_area(self):
        full = AVP(); full.configure(_default_config())
        lean = AVP(); lean.configure(_default_config(support_softmax=False, support_layernorm=False))
        assert lean.total_area_um2() < full.total_area_um2()


class TestAVPState:

    def test_snapshot_idle_initially(self):
        m = AVP()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False and s.current_op is None


class TestAVPNumericalModel:
    """SPEC-004 §7 conformance for the paired golden model."""

    def test_registered_and_paired(self):
        model = NumericalModelRegistry.create("AVP", "golden", _default_config())
        assert isinstance(model, AVPGoldenModel)
        assert AVPGoldenModel.for_module_type() == AVP.module_type()

    def test_supported_capabilities_subset_of_declared(self):
        declared = {c.name for c in AVP.declared_capabilities()}
        assert set(AVPGoldenModel.supported_capabilities()).issubset(declared)

    def test_softmax_sums_to_one(self):
        model = AVPGoldenModel()
        model.configure(_default_config())
        x = np.array([[1.0, 2.0, 3.0], [1.0, 1.0, 1.0]], dtype=np.float32)
        out = model.execute(_make_op("softmax"), {"in_data": Tensor(x, NumericDType.FP32, (2, 3))})
        np.testing.assert_allclose(out["out_data"].data.sum(axis=-1), [1.0, 1.0], rtol=1e-5)

    def test_layernorm_zero_mean_unit_var(self):
        model = AVPGoldenModel()
        model.configure(_default_config())
        x = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)
        out = model.execute(_make_op("layernorm"), {"in_data": Tensor(x, NumericDType.FP32, (1, 4))})
        np.testing.assert_allclose(out["out_data"].data.mean(axis=-1), [0.0], atol=1e-5)
        np.testing.assert_allclose(out["out_data"].data.var(axis=-1), [1.0], atol=1e-3)

    def test_gelu_default_matches_reference(self):
        model = AVPGoldenModel()
        model.configure(_default_config())
        x = np.array([0.0, 1.0, -1.0], dtype=np.float32)
        out = model.execute(_make_op("gelu"), {"in_data": Tensor(x, NumericDType.FP32, (3,))})
        c = np.float32(np.sqrt(2.0 / np.pi))
        ref = 0.5 * x * (1.0 + np.tanh(c * (x + np.float32(0.044715) * x**3)))
        np.testing.assert_allclose(out["out_data"].data, ref, rtol=1e-5)
        assert out["out_data"].dtype == NumericDType.FP32

    def test_execute_does_not_mutate_inputs(self):
        model = AVPGoldenModel()
        model.configure(_default_config())
        x = np.array([0.0, 1.0, -1.0], dtype=np.float32)
        original = x.copy()
        model.execute(_make_op("gelu"), {"in_data": Tensor(x, NumericDType.FP32, (3,))})
        np.testing.assert_array_equal(x, original)
