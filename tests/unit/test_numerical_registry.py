"""Tests for NumericalModelRegistry. Reference: SPEC-004 §3.3."""

from __future__ import annotations

import pytest

from npu_sim.core.errors import (
    DuplicateNumericalModelError,
    UnknownNumericalModelError,
)
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import (
    FIDELITY_BIT_ACCURATE,
    FIDELITY_FAST,
    FIDELITY_GOLDEN,
    FidelityLevel,
    INumericalModel,
)


def _make_model_class(
    module_type: str,
    fidelity: FidelityLevel,
    supported: tuple[str, ...] = (),
) -> type[INumericalModel]:

    class _GeneratedModel(INumericalModel):
        @classmethod
        def for_module_type(cls):
            return module_type

        @classmethod
        def model_version(cls):
            return "1.0.0"

        @classmethod
        def fidelity_level(cls):
            return fidelity

        @classmethod
        def supported_capabilities(cls):
            return list(supported)

        def configure(self, config):
            self._cfg = config

        def reset(self):
            pass

        def execute(self, operation, inputs):
            return inputs

    _GeneratedModel.__name__ = f"{module_type}_{fidelity.name}"
    return _GeneratedModel


class TestNumericalRegistry:

    def test_register_and_create(self, isolated_numerical_registry):
        cls = _make_model_class("Alpha", FIDELITY_GOLDEN)
        isolated_numerical_registry.register(cls)
        inst = isolated_numerical_registry.create("Alpha", "golden", {})
        assert isinstance(inst, cls)

    def test_duplicate_registration_rejected(self, isolated_numerical_registry):
        cls_a = _make_model_class("Beta", FIDELITY_GOLDEN)
        cls_b = _make_model_class("Beta", FIDELITY_GOLDEN)
        isolated_numerical_registry.register(cls_a)
        with pytest.raises(DuplicateNumericalModelError):
            isolated_numerical_registry.register(cls_b)

    def test_unknown_without_fallback_raises(self, isolated_numerical_registry):
        with pytest.raises(UnknownNumericalModelError):
            isolated_numerical_registry.create("Nope", "golden", {})

    def test_fast_falls_back_to_golden(self, isolated_numerical_registry):
        """Per SPEC-004 §3.3: if requested fidelity missing, fall back to golden."""
        gold_cls = _make_model_class("Gamma", FIDELITY_GOLDEN)
        isolated_numerical_registry.register(gold_cls)
        # 'fast' not registered → must fall back to 'golden'.
        inst = isolated_numerical_registry.create("Gamma", "fast", {})
        assert isinstance(inst, gold_cls)

    def test_no_fallback_if_golden_also_missing(self, isolated_numerical_registry):
        bit_cls = _make_model_class("Delta", FIDELITY_BIT_ACCURATE)
        isolated_numerical_registry.register(bit_cls)
        # Requesting 'fast' with only 'bit_accurate' present → no fallback.
        with pytest.raises(UnknownNumericalModelError):
            isolated_numerical_registry.create("Delta", "fast", {})

    def test_list_for_returns_registered_fidelities(self, isolated_numerical_registry):
        isolated_numerical_registry.register(_make_model_class("Epsilon", FIDELITY_GOLDEN))
        isolated_numerical_registry.register(_make_model_class("Epsilon", FIDELITY_FAST))
        isolated_numerical_registry.register(_make_model_class("Epsilon", FIDELITY_BIT_ACCURATE))
        assert isolated_numerical_registry.list_for("Epsilon") == sorted(
            ["golden", "fast", "bit_accurate"]
        )
        assert isolated_numerical_registry.list_for("NotRegistered") == []
