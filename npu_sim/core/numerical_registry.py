"""Functional-sim numerical model factory.

Reference: SPEC-004 §3.3.
"""

from __future__ import annotations

from npu_sim.core.errors import (
    DuplicateNumericalModelError,
    UnknownNumericalModelError,
)
from npu_sim.interfaces.numerical import FIDELITY_GOLDEN, INumericalModel


class NumericalModelRegistry:
    """Functional-sim factory keyed by (module_type, fidelity_level_name).

    Reference: SPEC-004 §3.3.
    """

    _registry: dict[tuple[str, str], type[INumericalModel]] = {}

    @classmethod
    def register(cls, model_class: type[INumericalModel]) -> type[INumericalModel]:
        key = (model_class.for_module_type(), model_class.fidelity_level().name)
        if key in cls._registry and cls._registry[key] is not model_class:
            raise DuplicateNumericalModelError(
                f"Numerical model for {key} already registered by {cls._registry[key]!r}."
            )
        cls._registry[key] = model_class
        return model_class

    @classmethod
    def create(
        cls,
        module_type: str,
        fidelity: str,
        config: dict,
    ) -> INumericalModel:
        """Instantiate a numerical model.

        Per SPEC-004 §3.3, falls back to `golden` if the requested fidelity
        is not registered.
        """
        key = (module_type, fidelity)
        if key not in cls._registry:
            fallback_key = (module_type, FIDELITY_GOLDEN.name)
            if fidelity != FIDELITY_GOLDEN.name and fallback_key in cls._registry:
                key = fallback_key
            else:
                raise UnknownNumericalModelError(
                    f"No numerical model registered for {key} and no golden fallback."
                )

        model = cls._registry[key]()
        model.configure(config)
        return model

    @classmethod
    def list_for(cls, module_type: str) -> list[str]:
        return sorted(fid for (mt, fid) in cls._registry if mt == module_type)

    @classmethod
    def _clear_for_test(cls) -> None:
        cls._registry.clear()
