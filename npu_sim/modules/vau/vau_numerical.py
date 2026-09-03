"""Golden numerical model paired with the VAU IModule.

Reference: SPEC-005 §4.8, SPEC-004 §3.1 / §4.1. Selects the elementwise op from
``operation.op_type``: ``add``/``mul``/``max`` are binary (need in_a + in_b;
missing in_b degrades to identity), ``relu`` is unary, default identity.
"""

from __future__ import annotations

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
class VAUGoldenModel(INumericalModel):
    """Golden-fidelity elementwise vector ALU."""

    @classmethod
    def for_module_type(cls) -> str:
        return "VAU"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["vector_add", "vector_mul"]

    def __init__(self) -> None:
        pass

    def configure(self, config: dict) -> None:
        pass  # stateless

    def reset(self) -> None:
        pass

    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        a = inputs.get("in_a")
        if a is None:
            return {}
        b = inputs.get("in_b")
        op = operation.op_type

        if op == "relu":
            result = np.maximum(a.data, 0)
        elif op in ("add", "mul", "max") and b is not None:
            if op == "add":
                result = a.data + b.data
            elif op == "mul":
                result = a.data * b.data
            else:
                result = np.maximum(a.data, b.data)
        else:
            result = a.data.copy()

        return {
            "out": Tensor(
                data=result,
                dtype=a.dtype,
                shape=a.shape,
                metadata={**a.metadata, "vau": True},
            )
        }
