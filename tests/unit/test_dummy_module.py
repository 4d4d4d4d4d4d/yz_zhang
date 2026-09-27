"""Conformance tests for the Dummy module against SPEC-001 §6 template."""

from __future__ import annotations

import jsonschema
import numpy as np
import pytest

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.modules.dummy import Dummy, DummyGoldenModel


def _default_config() -> dict:
    return {
        "throughput_elems_per_cycle": 2,
        "support_extra": True,
        "internal_fifo_depth": 8,
    }


def _make_op(required_caps: tuple[str, ...] = ("passthrough",), n: int = 16) -> StaticOperation:
    return StaticOperation(
        _op_type="passthrough",
        _required_capabilities=required_caps,
        _shape_info=(("n_elements", n),),
        _precision=Precision(kind=PrecisionKind.FP32),
    )


class TestDummyClassMetadata:

    def test_module_type_is_dummy(self):
        assert Dummy.module_type() == "Dummy"

    def test_module_version_is_semver(self):
        v = Dummy.module_version()
        parts = v.split(".")
        assert len(parts) == 3 and all(p.isdigit() for p in parts), v

    def test_config_schema_is_valid_json_schema(self):
        jsonschema.Draft7Validator.check_schema(Dummy.config_schema())

    def test_default_config_validates(self):
        jsonschema.validate(_default_config(), Dummy.config_schema())

    def test_invalid_config_rejected(self):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(
                {"throughput_elems_per_cycle": 999},  # exceeds max
                Dummy.config_schema(),
            )

    def test_capability_dependencies_consistent(self):
        caps = Dummy.declared_capabilities()
        names = {c.name for c in caps}
        for c in caps:
            for dep in c.depends_on:
                assert dep in names

    def test_port_specs_have_unique_names(self):
        names = [p.name for p in Dummy.port_specs()]
        assert len(names) == len(set(names))


class TestDummyRegistry:

    def test_dummy_is_registered(self):
        assert "Dummy" in ModuleRegistry.list_modules()

    def test_create_via_registry(self):
        inst = ModuleRegistry.create("Dummy", _default_config())
        assert isinstance(inst, Dummy)


class TestDummyLifecycle:

    def test_configure_sets_active_capabilities(self, event_bus, stat_sink):
        from npu_sim.interfaces.clock import IClock

        class _StubClock(IClock):
            @property
            def domain_id(self): return "main_clk"
            @property
            def period_ps(self): return 1000
            def current_time_ps(self): return 0
            def current_cycle(self): return 0
            def wait_cycles(self, n): pass
            def wait_until_ps(self, t): pass
            def wait_event(self, e): pass
            def is_same_domain(self, other): return False

        m = Dummy()
        m.bind_services(event_bus, stat_sink, _StubClock())
        m.configure(_default_config())
        assert "passthrough" in m.active_capabilities()
        assert "extra" in m.active_capabilities()

    def test_configure_without_extra(self):
        cfg = _default_config()
        cfg["support_extra"] = False
        m = Dummy()
        # Skip bind_services for this assertion (configure does not depend on it).
        m.configure(cfg)
        assert "extra" not in m.active_capabilities()

    def test_configure_only_once(self):
        m = Dummy()
        m.configure(_default_config())
        with pytest.raises(RuntimeError):
            m.configure(_default_config())


class TestDummyCapabilityQueries:

    def _make_configured(self) -> Dummy:
        m = Dummy()
        m.configure(_default_config())
        return m

    def test_can_execute_consistency(self):
        m = self._make_configured()
        op = _make_op(required_caps=("passthrough",))
        # The contract: required must be subset of active.
        assert m.can_execute(op) == set(op.required_capabilities).issubset(
            set(m.active_capabilities())
        )

    def test_can_execute_rejects_missing_capability(self):
        m = self._make_configured()
        op = _make_op(required_caps=("nonexistent_capability",))
        assert not m.can_execute(op)

    def test_estimate_latency_is_pure(self):
        m = self._make_configured()
        op = _make_op(n=32)
        e1 = m.estimate_latency(op)
        e2 = m.estimate_latency(op)
        assert e1 == e2

    def test_estimate_energy_is_pure(self):
        m = self._make_configured()
        op = _make_op(n=32)
        e1 = m.estimate_energy(op)
        e2 = m.estimate_energy(op)
        assert e1 == e2


class TestDummyAreaPowerAggregation:

    def test_total_area_um2_equals_active_capability_sum(self):
        m = Dummy()
        m.configure(_default_config())
        expected = sum(
            cap.area_cost_um2
            for cap in Dummy.declared_capabilities()
            if cap.name in m.active_capabilities()
        )
        assert m.total_area_um2() == expected

    def test_static_power_uw_equals_active_capability_sum(self):
        m = Dummy()
        m.configure(_default_config())
        expected = sum(
            cap.static_power_uw
            for cap in Dummy.declared_capabilities()
            if cap.name in m.active_capabilities()
        )
        assert m.static_power_uw() == expected

    def test_disabling_extra_reduces_area(self):
        m_full = Dummy()
        m_full.configure(_default_config())

        cfg = _default_config()
        cfg["support_extra"] = False
        m_lean = Dummy()
        m_lean.configure(cfg)

        assert m_lean.total_area_um2() < m_full.total_area_um2()


class TestDummyState:

    def test_snapshot_state_returns_idle_initially(self):
        m = Dummy()
        m.configure(_default_config())
        s = m.snapshot_state()
        assert s.busy is False
        assert s.current_op is None


class TestDummyNumericalModel:
    """SPEC-004 §7 conformance tests for the paired numerical model."""

    def test_pairs_with_module_type(self):
        assert DummyGoldenModel.for_module_type() == Dummy.module_type()

    def test_supported_capabilities_is_subset(self):
        declared = {c.name for c in Dummy.declared_capabilities()}
        supported = set(DummyGoldenModel.supported_capabilities())
        assert supported.issubset(declared)

    def test_execute_is_pure(self):
        model = DummyGoldenModel()
        model.configure(_default_config())
        op = _make_op()
        inputs = {
            "in_data": Tensor(
                data=np.arange(16, dtype=np.float32),
                dtype=NumericDType.FP32,
                shape=(16,),
            )
        }
        out1 = model.execute(op, inputs)
        out2 = model.execute(op, inputs)
        np.testing.assert_array_equal(out1["in_data"].data, out2["in_data"].data)

    def test_execute_does_not_mutate_inputs(self):
        model = DummyGoldenModel()
        model.configure(_default_config())
        op = _make_op()
        arr = np.arange(16, dtype=np.float32)
        original = arr.copy()
        inputs = {
            "in_data": Tensor(data=arr, dtype=NumericDType.FP32, shape=(16,))
        }
        _ = model.execute(op, inputs)
        np.testing.assert_array_equal(inputs["in_data"].data, original)

    def test_passthrough_matches_input(self):
        model = DummyGoldenModel()
        model.configure(_default_config())
        op = _make_op()
        arr = np.random.rand(16).astype(np.float32)
        inputs = {"in_data": Tensor(data=arr, dtype=NumericDType.FP32, shape=(16,))}
        out = model.execute(op, inputs)
        np.testing.assert_array_equal(out["in_data"].data, arr)


