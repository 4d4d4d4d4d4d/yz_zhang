"""Golden numerical model paired with the AVP IModule.

Reference: SPEC-005 §5.8, SPEC-004 §3.1 / §4.1. Selects the activation from
``operation.op_type``: gelu (tanh approximation, default), softmax / layernorm
along the last axis, relu fallback. Output is FP32.
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

_GELU_C = np.float32(np.sqrt(2.0 / np.pi))


def _gelu(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    return 0.5 * x * (1.0 + np.tanh(_GELU_C * (x + np.float32(0.044715) * x**3)))


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    shifted = x - np.max(x, axis=-1, keepdims=True)
    e = np.exp(shifted)
    return e / np.sum(e, axis=-1, keepdims=True)


def _layernorm(x: np.ndarray, eps: float = 1e-5) -> np.ndarray:
    x = x.astype(np.float32)
    mean = np.mean(x, axis=-1, keepdims=True)
    var = np.var(x, axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(var + np.float32(eps))


@NumericalModelRegistry.register
class AVPGoldenModel(INumericalModel):
    """Golden-fidelity activation / normalization."""

    @classmethod
    def for_module_type(cls) -> str:
        return "AVP"

    @classmethod
    def model_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def fidelity_level(cls) -> FidelityLevel:
        return FIDELITY_GOLDEN

    @classmethod
    def supported_capabilities(cls) -> list[str]:
        return ["gelu"]

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
        t = inputs.get("in_data")
        if t is None:
            return {}
        op = operation.op_type

        if op == "softmax":
            result = _softmax(t.data)
        elif op == "layernorm":
            result = _layernorm(t.data)
        elif op == "relu":
            result = np.maximum(t.data, 0).astype(np.float32)
        else:  # gelu default
            result = _gelu(t.data)

        return {
            "out_data": Tensor(
                data=result,
                dtype=NumericDType.FP32,
                shape=t.shape,
                metadata={**t.metadata, "activated": True},
            )
        }
