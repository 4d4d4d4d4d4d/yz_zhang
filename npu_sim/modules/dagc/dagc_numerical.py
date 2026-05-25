"""Golden numerical model paired with the DAGC IModule.

Reference: SPEC-004 §3.1 (pure function, no mutation), §4.1 (paired by
module_type). DAGC unpacks block-floating-point data into a wide FP32 stream;
the golden model performs the dequantization ``value * scale`` (block scale)
and casts to FP32. With no scale it degrades to a plain widening cast.
"""

from __future__ import annotations

from typing import Optional

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
class DAGCGoldenModel(INumericalModel):
    """Golden-fidelity unpack: dequantize BFP blocks to FP32."""

    @classmethod
    def for_module_type(cls) -> str:
        return "DAGC"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["bfp8_unpack", "bfp16_unpack"]

    def __init__(self) -> None:
        self._config: Optional[dict] = None

    def configure(self, config: dict) -> None:
        self._config = config

    def reset(self) -> None:
        pass  # stateless unpack

    def execute(
        self,
        operation: IOperation,
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        outputs: dict[str, Tensor] = {}
        for name, t in inputs.items():
            unpacked = t.data.astype(np.float32, copy=True)
            if t.scale is not None:
                unpacked = unpacked * np.asarray(t.scale, dtype=np.float32)
            outputs[name] = Tensor(
                data=unpacked,
                dtype=NumericDType.FP32,
                shape=t.shape,
                metadata={**t.metadata, "unpacked": True},
            )
        return outputs
