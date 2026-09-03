"""Conformance tests for the MAC module. SPEC-005 §6.1/§6.2, SPEC-001 §6, SPEC-004 §7."""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.mac import MAC, MACGoldenModel


def _default_config(**overrides) -> dict:
    cfg = {"array_rows": 32, "array_cols": 32, "support_bfp16": True, "support_fp16": False}
    cfg.update(overrides)
    return cfg


def _make_op(required_caps=("int8_matmul",), m=8, k=8, n=8,
             kind=PrecisionKind.INT8) -> StaticOperation:
    return StaticOperation(
        _op_type="matmul",
        _required_capabilities=required_caps,
        _shape_info=(("m", m), ("k", k), ("n", n)),
        _precision=Precision(kind=kind),
    )


class TestMACClassMetadata:
    """SPEC-001 §6 class-level conformance."""

    def test_module_type(self):
        assert MAC.module_type() == "MAC"

    def test_module_version_is_semver(self):
        parts = MAC.module_version().split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(MAC.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), MAC.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"array_rows": 2, "array_cols": 32}, MAC.config_schema())

    def test_required_fields_enforced(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"array_rows": 32}, MAC.config_schema())

    def test_capability_dependencies_consistent(self):
        names = {c.name for c in MAC.declared_capabilities()}
        for c in MAC.declared_capabilities():
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in MAC.port_specs()]
        assert len(names) == len(set(names))


class TestMACRegistry:

    def test_registered(self):
        assert "MAC" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        assert isinstance(ModuleRegistry.create("MAC", _default_config()), MAC)


class TestMACLifecycle:

    def test_default_activates_int8_and_bfp16(self):
        m = MAC()
        m.configure(_default_config())
        assert set(m.active_capabilities()) == {"int8_matmul", "accumulate_fp32", "bfp16_matmul"}

    def test_fp16_gated_by_flag(self):
        m = MAC()
        m.configure(_default_config(support_fp16=True))
        assert "fp16_matmul" in m.active_capabilities()

    def test_disabling_bfp16_drops_capability(self):
        m = MAC()
        m.configure(_default_config(support_bfp16=False))
        assert set(m.active_capabilities()) == {"int8_matmul", "accumulate_fp32"}

    def test_configure_only_once(self):
        m = MAC()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())

    def test_ports_exposed_after_configure(self):
        m = MAC()
        m.configure(_default_config())
        assert set(m.input_ports()) == {"in_act", "in_weight", "in_cmd"}
        assert set(m.output_ports()) == {"out_psum"}


class TestMACCapabilityQueries:

    def _configured(self) -> MAC:
        m = MAC()
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
        op = _make_op()
        assert m.estimate_latency(op) == m.estimate_latency(op)

    def test_bigger_gemm_costs_more_cycles(self):
        m = self._configured()
        small = m.estimate_latency(_make_op(m=8, k=8, n=8))
        big = m.estimate_latency(_make_op(m=64, k=64, n=64))
        assert big.min_cycles > small.min_cycles

    def test_unsupported_precision_zero_cycles(self):
        # fp16 disabled by default -> not supported.
        m = self._configured()
        assert m.estimate_latency(_make_op(kind=PrecisionKind.FP16)).min_cycles == 0

    def test_larger_array_is_faster(self):
        small = MAC(); small.configure(_default_config(array_rows=8, array_cols=8))
        big = MAC(); big.configure(_default_config(array_rows=128, array_cols=128))
        op = _make_op(m=64, k=64, n=64)
        assert big.estimate_latency(op).min_cycles < small.estimate_latency(op).min_cycles

    def test_estimate_energy_is_pure(self):
        m = self._configured()
        op = _make_op()
        assert m.estimate_energy(op) == m.estimate_energy(op)


class TestMACAreaPower:
    """SPEC-013 physical model: area = PE count × per-PE gates × cell area."""

    def test_area_matches_physical_model(self):
        from npu_sim import physical
        m = MAC()
        m.configure(_default_config())
        expected = physical.mac_array_area_um2(32, 32, m.active_capabilities())
        assert m.total_area_um2() == pytest.approx(expected)
        assert expected > 0  # grounded, non-zero

    def test_area_scales_with_pe_count(self):
        small = MAC(); small.configure(_default_config(array_rows=16, array_cols=16))
        big = MAC(); big.configure(_default_config(array_rows=32, array_cols=32))
        # 4× the PEs → 4× the area (physically ∝ PE count)
        assert big.total_area_um2() == pytest.approx(4 * small.total_area_um2())

    def test_dropping_bfp16_reduces_area(self):
        full = MAC(); full.configure(_default_config())
        lean = MAC(); lean.configure(_default_config(support_bfp16=False))
        assert lean.total_area_um2() < full.total_area_um2()

    def test_energy_per_mac_is_horowitz_grounded(self):
        from npu_sim import physical
        m = MAC(); m.configure(_default_config())
        op = _make_op(m=8, k=8, n=8, kind=PrecisionKind.INT8)  # 512 MACs
        e = m.estimate_energy(op)
        assert e.dynamic_pj == pytest.approx(512 * physical.energy_per_mac_pj("int8"))


class TestMACTimingModel:
    """finding #2 resolved: runtime and estimate share one systolic model."""

    def _tok(self, dim):
        from npu_sim.interfaces.transport import TransportToken
        return TransportToken(
            payload=None, size_bytes=1, timestamp_ps=0, source_module="x",
            metadata={"op_shape": {"m": dim, "k": dim, "n": dim}},
        )

    def test_runtime_and_estimate_agree(self):
        m = MAC(); m.configure(_default_config())
        op = _make_op(m=32, k=32, n=32, kind=PrecisionKind.INT8)
        est_min = m.estimate_latency(op).min_cycles
        assert m._compute_cycles(self._tok(32)) == est_min
        assert est_min > 2  # scales with the matmul, not a flat constant

    def test_runtime_scales_with_matmul_size(self):
        m = MAC(); m.configure(_default_config())
        assert m._compute_cycles(self._tok(64)) > m._compute_cycles(self._tok(32))

    def test_shapeless_token_uses_base_cost(self):
        from npu_sim.interfaces.transport import TransportToken
        m = MAC(); m.configure(_default_config())
        tok = TransportToken(payload=None, size_bytes=1, timestamp_ps=0,
                             source_module="x", metadata={})
        assert m._compute_cycles(tok) == max(1, 32 // 32) + 1


class TestMACState:

    def test_snapshot_idle_initially(self):
        m = MAC()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False and s.current_op is None


class TestMACNumericalModel:
    """SPEC-004 §7 conformance for the paired golden model."""

    def test_registered_and_paired(self):
        model = NumericalModelRegistry.create("MAC", "golden", _default_config())
        assert isinstance(model, MACGoldenModel)
        assert MACGoldenModel.for_module_type() == MAC.module_type()

    def test_supported_capabilities_subset_of_declared(self):
        declared = {c.name for c in MAC.declared_capabilities()}
        assert set(MACGoldenModel.supported_capabilities()).issubset(declared)

    def test_matmul_is_correct(self):
        model = MACGoldenModel()
        model.configure(_default_config())
        act = np.arange(6, dtype=np.int8).reshape(2, 3)
        weight = np.arange(12, dtype=np.int8).reshape(3, 4)
        out = model.execute(
            _make_op(),
            {
                "in_act": Tensor(act, NumericDType.INT8, (2, 3)),
                "in_weight": Tensor(weight, NumericDType.INT8, (3, 4)),
            },
        )
        np.testing.assert_array_equal(
            out["out_psum"].data, act.astype(np.float32) @ weight.astype(np.float32)
        )
        assert out["out_psum"].dtype == NumericDType.FP32

    def test_passthrough_when_no_weight(self):
        model = MACGoldenModel()
        model.configure(_default_config())
        act = np.arange(6, dtype=np.int8).reshape(2, 3)
        out = model.execute(_make_op(), {"in_act": Tensor(act, NumericDType.INT8, (2, 3))})
        np.testing.assert_array_equal(out["out_psum"].data, act.astype(np.float32))

    def test_execute_does_not_mutate_inputs(self):
        model = MACGoldenModel()
        model.configure(_default_config())
        act = np.arange(6, dtype=np.int8).reshape(2, 3)
        original = act.copy()
        model.execute(_make_op(), {"in_act": Tensor(act, NumericDType.INT8, (2, 3))})
        np.testing.assert_array_equal(act, original)
