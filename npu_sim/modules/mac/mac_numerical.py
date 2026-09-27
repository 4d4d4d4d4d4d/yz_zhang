"""Golden numerical model paired with the MAC IModule.

Reference: SPEC-005 §3.8, SPEC-004 §3.1 / §4.1. When both an activation and a
weight tensor are present (2D, conformable), computes the FP32 matmul
``out_psum = act @ weight``; otherwise degrades to an FP32 widening copy of the
activation (weights not yet loaded).
"""

from __future__ import annotations

import numpy as np

from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.interfaces.numerical import (
    FIDELITY_GOLDEN,
    FidelityLevel,
    INumericalModel,
    NumericDType,
    Tensor,
)
from npu_sim.interfaces.operation import IOperation


@NumericalModelRegistry.register
class MACGoldenModel(INumericalModel):
    """Golden-fidelity GEMM with FP32 accumulation."""

    @classmethod
    def for_module_type(cls) -> str:
        return "MAC"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["int8_matmul", "accumulate_fp32"]

    def __init__(self) -> None:
        pass

    def configure(self, config: dict) -> None:
        pass  # stateless GEMM

    def reset(self) -> None:
        pass

    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        act = inputs.get("in_act")
        weight = inputs.get("in_weight")
        if act is None:
            return {}

        if (
            weight is not None
            and act.data.ndim == 2
            and weight.data.ndim == 2
            and act.data.shape[1] == weight.data.shape[0]
        ):
            psum = act.data.astype(np.float32) @ weight.data.astype(np.float32)
        else:
            # Weights not loaded / non-conformable: FP32 widening passthrough.
            psum = act.data.astype(np.float32, copy=True)

        return {
            "out_psum": Tensor(
                data=psum,
                dtype=NumericDType.FP32,
                shape=psum.shape,
                metadata={**act.metadata, "psum": True},
            )
        }
