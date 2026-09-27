"""Dummy numerical model paired with Dummy IModule.

Reference: SPEC-004 §3.1, §4.1 (paired by module_type).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import (
    FIDELITY_GOLDEN,
    FidelityLevel,
    INumericalModel,
    Tensor,
)
from npu_sim.interfaces.operation import IOperation


@NumericalModelRegistry.register
class DummyGoldenModel(INumericalModel):
    """Golden-fidelity numerical model for Dummy: pure passthrough."""

    @classmethod
    def for_module_type(cls) -> str:
        return "Dummy"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["passthrough", "extra"]

    def __init__(self) -> None:
        self._support_extra: bool = False
        self._config: Optional[dict] = None

    def configure(self, config: dict) -> None:
        self._config = config
        self._support_extra = config.get("support_extra", False)

    def reset(self) -> None:
        pass  # passthrough is stateless

    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        # Pure passthrough: copy data to honor "must not mutate inputs" contract.
        outputs: dict[str, Tensor] = {}
        for name, t in inputs.items():
            outputs[name] = Tensor(
                data=np.array(t.data, copy=True),
                dtype=t.dtype,
                shape=t.shape,
                scale=t.scale,
                zero_point=t.zero_point,
                metadata=dict(t.metadata),
            )
        return outputs
