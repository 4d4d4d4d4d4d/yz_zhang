"""INumericalModel and supporting types for functional simulation.

Reference: SPEC-004 §3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class NumericDType(Enum):
    """Numeric data types tracked by functional sim. Reference: SPEC-004 §3.1."""

    INT4 = "int4"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    FP16 = "fp16"
    BF16 = "bf16"
    FP32 = "fp32"
    BFP8 = "bfp8"
    BFP16 = "bfp16"


@dataclass(frozen=True)
class Tensor:
    """Functional sim data unit. Reference: SPEC-004 §3.1."""

    data: np.ndarray
    dtype: NumericDType
    shape: tuple[int, ...]
    scale: Optional[np.ndarray] = None
    zero_point: Optional[np.ndarray] = None
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FidelityLevel:
    """Reference: SPEC-004 §3.2."""

    name: str
    description: str


# Standard fidelity levels per SPEC-004 §3.2.
FIDELITY_GOLDEN = FidelityLevel("golden", "High-precision reference (FP32/FP64).")
FIDELITY_BIT_ACCURATE = FidelityLevel("bit_accurate", "Bit-exact match with RTL.")
FIDELITY_FAST = FidelityLevel("fast", "Mathematical approximation.")


class INumericalModel(ABC):
    """Per-IModule functional / numerical model. Pure function, no timing.

    Reference: SPEC-004 §3.1.
    """

    @classmethod
    @abstractmethod
    def for_module_type(cls) -> str:
        """The IModule.module_type() this model is paired with."""

    @classmethod
    @abstractmethod
    def model_version(cls) -> str:
        """semver."""

    @classmethod
    @abstractmethod
    def fidelity_level(cls) -> FidelityLevel: ...

    @classmethod
    @abstractmethod
    def supported_capabilities(cls) -> list[str]:
        """Capability names this model implements. Must be a subset of the
        paired IModule.declared_capabilities() names.
        """

    @abstractmethod
    def configure(self, config: dict) -> None:
        """Configure with the same dict accepted by the paired IModule."""

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def execute(
        self,
        operation: "IOperation",
        inputs: dict[str, Tensor],
    ) -> dict[str, Tensor]:
        """Execute the op. Pure function. Reference: SPEC-004 §3.1 constraints."""


@dataclass(frozen=True)
class Tolerance:
    """Per-output tensor tolerance. Reference: SPEC-004 §5.2."""

    rtol: float = 1e-5
    atol: float = 1e-8
    max_abs_error: Optional[float] = None
    max_rel_error: Optional[float] = None
    min_cosine_sim: Optional[float] = None
    max_outliers_pct: float = 0.0


@dataclass(frozen=True)
class ToleranceViolation:
    metric: str
    actual: float
    threshold: float


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    metrics: dict[str, float]
    violations: list[ToleranceViolation] = field(default_factory=list)
    sample_diff: Optional[np.ndarray] = None
