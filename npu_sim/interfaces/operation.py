"""IOperation: the contract between Mapper and Module.

Reference: SPEC-001 §3.2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class PrecisionKind(Enum):
    """Numeric precision categories used by op routing.

    Reference: SPEC-001 §3.2 (referenced as `Precision`) and SPEC-004 §3.1.
    """

    INT4 = "int4"
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    FP16 = "fp16"
    BF16 = "bf16"
    FP32 = "fp32"
    BFP8 = "bfp8"
    BFP16 = "bfp16"
    MIXED_BFP8_BFP16 = "mixed_bfp8_bfp16"


@dataclass(frozen=True)
class Precision:
    """Composite precision descriptor.

    For ops that take multiple operands at different precisions
    (e.g. BFP8 weight x BFP16 activation), `operands` lists each.
    """

    kind: PrecisionKind
    operands: tuple[PrecisionKind, ...] = ()

    def is_bfp8(self) -> bool:
        return self.kind == PrecisionKind.BFP8

    def is_bfp16(self) -> bool:
        return self.kind == PrecisionKind.BFP16

    def is_mixed_bfp8_bfp16(self) -> bool:
        return self.kind == PrecisionKind.MIXED_BFP8_BFP16


class IOperation(ABC):
    """An operation descriptor. Mapper parses a model into a list of IOperations."""

    @property
    @abstractmethod
    def op_type(self) -> str:
        """Operation type name, e.g. "matmul", "softmax", "layernorm"."""

    @property
    @abstractmethod
    def required_capabilities(self) -> list[str]:
        """Capability names required to execute this op.

        This is the contract language between Mapper and Module:
        a module can execute an op iff every required capability is in
        the module's `active_capabilities()`.

        Reference: SPEC-001 §3.1 IModule.can_execute().
        """

    @property
    @abstractmethod
    def shape_info(self) -> dict:
        """Shape / size information used by estimate_latency / estimate_energy."""

    @property
    @abstractmethod
    def precision(self) -> Precision:
        """Precision descriptor."""


@dataclass(frozen=True)
class StaticOperation(IOperation):
    """A simple immutable IOperation used by tests and rule-based mapping."""

    _op_type: str
    _required_capabilities: tuple[str, ...]
    _shape_info: tuple[tuple[str, int], ...]
    _precision: Precision

    @property
    def op_type(self) -> str:
        return self._op_type

    @property
    def required_capabilities(self) -> list[str]:
        return list(self._required_capabilities)

    @property
    def shape_info(self) -> dict:
        return dict(self._shape_info)

    @property
    def precision(self) -> Precision:
        return self._precision
