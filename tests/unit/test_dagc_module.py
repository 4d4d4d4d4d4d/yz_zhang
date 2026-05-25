"""Conformance tests for the DAGC module against the SPEC-001 §6 template.

DAGC is the first real NPU module (SPEC-001 §5 canonical example). Paired
numerical model tests follow SPEC-004 §7.
"""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.dagc import DAGC, DAGCGoldenModel


def _default_config() -> dict:
    return {
        "bfp8_unpack_throughput": 4,
        "bfp16_unpack_throughput": 2,
        "bfp_ratio": "2:1",
        "support_4bit_reorder": True,
        "support_mixed_bfp8_bfp16": True,
        "join_fifo_depth": 16,
    }


def _make_op(
    required_caps: tuple[str, ...] = ("bfp8_unpack",),
    n: int = 64,
    kind: PrecisionKind = PrecisionKind.BFP8,
) -> StaticOperation:
    return StaticOperation(
        _op_type="unpack",
        _required_capabilities=required_caps,
        _shape_info=(("n_elements", n),),
        _precision=Precision(kind=kind),
    )


class TestDAGCClassMetadata:
    """SPEC-001 §6 class-level conformance."""

    def test_module_type_is_dagc(self):
        assert DAGC.module_type() == "DAGC"

    def test_module_version_is_semver(self):
        parts = DAGC.module_version().split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts)

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(DAGC.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), DAGC.config_schema())

    def test_invalid_config_rejected(self):
        # bfp8_unpack_throughput max is 8 per SPEC-001 §5.
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"bfp8_unpack_throughput": 99, "bfp16_unpack_throughput": 1},
                DAGC.config_schema(),
            )

    def test_required_fields_enforced(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"bfp8_unpack_throughput": 2}, DAGC.config_schema())

    def test_capability_dependencies_consistent(self):
        caps = DAGC.declared_capabilities()
        names = {c.name for c in caps}
        for c in caps:
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in DAGC.port_specs()]
        assert len(names) == len(set(names))


class TestDAGCRegistry:

    def test_dagc_is_registered(self):
        assert "DAGC" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        inst = ModuleRegistry.create("DAGC", _default_config())
        assert isinstance(inst, DAGC)


class TestDAGCLifecycle:

    def test_configure_activates_all_capabilities_by_default(self):
        m = DAGC()
        m.configure(_default_config())
        active = set(m.active_capabilities())
        assert active == {"bfp8_unpack", "bfp16_unpack", "bfp8_bfp16_mix", "int4_reorder"}

    def test_disabling_flags_drops_optional_capabilities(self):
        cfg = _default_config()
        cfg["support_4bit_reorder"] = False
        cfg["support_mixed_bfp8_bfp16"] = False
        m = DAGC()
        m.configure(cfg)
        assert set(m.active_capabilities()) == {"bfp8_unpack", "bfp16_unpack"}

    def test_configure_only_once(self):
        m = DAGC()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())

    def test_ports_exposed_after_configure(self):
        m = DAGC()
        m.configure(_default_config())
        assert set(m.input_ports()) == {"in_packed", "in_cmd"}
        assert set(m.output_ports()) == {"out_unpacked"}


class TestDAGCCapabilityQueries:

    def _configured(self) -> DAGC:
        m = DAGC()
        m.configure(_default_config())
        return m

    def test_can_execute_consistency(self):
        m = self._configured()
        op = _make_op(required_caps=("bfp8_unpack",))
        assert m.can_execute(op) == set(op.required_capabilities).issubset(
            set(m.active_capabilities())
        )

    def test_can_execute_rejects_missing_capability(self):
        m = self._configured()
        assert not m.can_execute(_make_op(required_caps=("nonexistent",)))

    def test_estimate_latency_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_latency(op) == m.estimate_latency(op)

    def test_latency_bfp16_slower_than_bfp8(self):
        # bfp16 lane throughput (2) < bfp8 lane (4), so same n costs more cycles.
        m = self._configured()
        n = 128
        bfp8 = m.estimate_latency(_make_op(n=n, kind=PrecisionKind.BFP8))
        bfp16 = m.estimate_latency(_make_op(n=n, kind=PrecisionKind.BFP16))
        assert bfp16.min_cycles > bfp8.min_cycles

    def test_unsupported_precision_zero_cycles(self):
        m = self._configured()
        est = m.estimate_latency(_make_op(n=128, kind=PrecisionKind.FP32))
        assert est.min_cycles == 0

    def test_estimate_energy_is_pure(self):
        m = self._configured()
        op = _make_op(n=128)
        assert m.estimate_energy(op) == m.estimate_energy(op)


class TestDAGCAreaPowerAggregation:
    """SPEC-001 §3.1 area / power = sum over active capabilities."""

    def test_total_area_equals_active_capability_sum(self):
        m = DAGC()
        m.configure(_default_config())
        expected = sum(
            c.area_cost_um2
            for c in DAGC.declared_capabilities()
            if c.name in m.active_capabilities()
        )
        assert m.total_area_um2() == expected

    def test_dropping_optional_capabilities_reduces_area(self):
        full = DAGC()
        full.configure(_default_config())

        cfg = _default_config()
        cfg["support_4bit_reorder"] = False
        cfg["support_mixed_bfp8_bfp16"] = False
        lean = DAGC()
        lean.configure(cfg)

        assert lean.total_area_um2() < full.total_area_um2()


class TestDAGCState:

    def test_snapshot_state_idle_initially(self):
        m = DAGC()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False
        assert s.current_op is None


class TestDAGCNumericalModel:
    """SPEC-004 §7 conformance for the paired golden model."""

    def test_registered_and_paired(self):
        model = NumericalModelRegistry.create("DAGC", "golden", _default_config())
        assert isinstance(model, DAGCGoldenModel)
        assert DAGCGoldenModel.for_module_type() == DAGC.module_type()

    def test_supported_capabilities_subset_of_declared(self):
        declared = {c.name for c in DAGC.declared_capabilities()}
        assert set(DAGCGoldenModel.supported_capabilities()).issubset(declared)

    def test_execute_is_pure(self):
        model = DAGCGoldenModel()
        model.configure(_default_config())
        op = _make_op()
        inputs = {
            "in_packed": Tensor(
                data=np.arange(8, dtype=np.int8),
                dtype=NumericDType.BFP8,
                shape=(8,),
            )
        }
        out1 = model.execute(op, inputs)
        out2 = model.execute(op, inputs)
        np.testing.assert_array_equal(out1["in_packed"].data, out2["in_packed"].data)

    def test_execute_does_not_mutate_inputs(self):
        model = DAGCGoldenModel()
        model.configure(_default_config())
        arr = np.arange(8, dtype=np.int8)
        original = arr.copy()
        inputs = {"in_packed": Tensor(data=arr, dtype=NumericDType.BFP8, shape=(8,))}
        model.execute(op := _make_op(), inputs)
        np.testing.assert_array_equal(inputs["in_packed"].data, original)

    def test_dequantizes_with_block_scale(self):
        model = DAGCGoldenModel()
        model.configure(_default_config())
        arr = np.array([1, 2, 3, 4], dtype=np.int8)
        inputs = {
            "in_packed": Tensor(
                data=arr,
                dtype=NumericDType.BFP8,
                shape=(4,),
                scale=np.float32(2.0),
            )
        }
        out = model.execute(_make_op(), inputs)
        np.testing.assert_array_equal(out["in_packed"].data, arr.astype(np.float32) * 2.0)
        assert out["in_packed"].dtype == NumericDType.FP32
