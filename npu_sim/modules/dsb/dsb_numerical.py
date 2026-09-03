"""Golden numerical model paired with the DSB IModule.

Reference: SPEC-005 §2.8, SPEC-004 §3.1 (pure function, no mutation), §4.1
(paired by module_type). Staging does not alter values: the golden model is an
identity copy, replicating along a new leading axis when broadcast_factor > 1.
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
class DSBGoldenModel(INumericalModel):
    """Golden-fidelity staging: identity copy (+ optional broadcast)."""

    @classmethod
    def for_module_type(cls) -> str:
        return "DSB"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["tile_buffer"]

    def __init__(self) -> None:
        self._broadcast_factor: int = 1

    def configure(self, config: dict) -> None:
        self._broadcast_factor = config.get("broadcast_factor", 1)

    def reset(self) -> None:
        pass  # stateless staging

    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        outputs: dict[str, Tensor] = {}
        for name, t in inputs.items():
            data = t.data.copy()
            shape = t.shape
            if self._broadcast_factor > 1:
                data = np.broadcast_to(data, (self._broadcast_factor, *data.shape)).copy()
                shape = (self._broadcast_factor, *shape)
            outputs[name] = Tensor(
                data=data,
                dtype=t.dtype,
                shape=shape,
                scale=t.scale,
                zero_point=t.zero_point,
                metadata={**t.metadata, "staged": True},
            )
        return outputs
