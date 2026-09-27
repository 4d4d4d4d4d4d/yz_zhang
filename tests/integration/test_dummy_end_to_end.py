"""End-to-end Phase 1 self-test: instantiate Dummy via both registries,
configure with the same DSL-style config, and verify identity-layer
consistency required by SPEC-001 §4.1 / SPEC-004 §4.1.
"""

from __future__ import annotations

import numpy as np

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import NumericDType, Tensor
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation


def test_module_and_numerical_share_identity():
    """SPEC-004 §4.1: module_type is the pairing key between IModule and INumericalModel."""

    config = {
        "throughput_elems_per_cycle": 2,
        "support_extra": True,
        "internal_fifo_depth": 8,
    }

    # Same config drives both registries.
    timing_module = ModuleRegistry.create("Dummy", config)
    timing_module.configure(config)

    numerical_model = NumericalModelRegistry.create("Dummy", "golden", config)

    # Numerical supported_capabilities must be subset of timing declared_capabilities.
    declared = {c.name for c in type(timing_module).declared_capabilities()}
    supported = set(type(numerical_model).supported_capabilities())
    assert supported.issubset(declared)


def test_functional_passthrough_matches_reference():
    """Use the Dummy golden model as a tiny reference loop, mirroring the
    SPEC-004 §6 use-case structure (compare-with-reference)."""

    config = {"throughput_elems_per_cycle": 1, "support_extra": False}
    model = NumericalModelRegistry.create("Dummy", "golden", config)

    op = StaticOperation(
        _op_type="passthrough",
        _required_capabilities=("passthrough",),
        _shape_info=(("n_elements", 64),),
        _precision=Precision(kind=PrecisionKind.FP32),
    )

    rng = np.random.default_rng(seed=42)
    data = rng.standard_normal(64).astype(np.float32)
    inputs = {"in_data": Tensor(data=data, dtype=NumericDType.FP32, shape=(64,))}

    outputs = model.execute(op, inputs)
    np.testing.assert_array_equal(outputs["in_data"].data, data)


def test_fast_fidelity_falls_back_to_golden_for_dummy():
    """Only golden Dummy model is registered; fast must transparently fall back."""

    config = {"throughput_elems_per_cycle": 1}
    inst = NumericalModelRegistry.create("Dummy", "fast", config)
    # The fallback returns the golden class.
    assert type(inst).fidelity_level().name == "golden"
