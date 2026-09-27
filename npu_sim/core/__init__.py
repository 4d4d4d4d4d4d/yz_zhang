"""Core platform services: registries, errors."""

from npu_sim.core.errors import (
    CircularReferenceError,
    DuplicateModuleTypeError,
    DuplicateNumericalModelError,
    InvalidMappingHintError,
    InvalidModuleTypeNameError,
    InvalidStallReport,
    MapperBugError,
    NpuSimError,
    OverrideError,
    PortNotFoundError,
    UnknownModuleTypeError,
    UnknownNumericalModelError,
)
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry

__all__ = [
    "CircularReferenceError",
    "DuplicateModuleTypeError",
    "DuplicateNumericalModelError",
    "InvalidMappingHintError",
    "InvalidModuleTypeNameError",
    "InvalidStallReport",
    "MapperBugError",
    "ModuleRegistry",
    "NpuSimError",
    "NumericalModelRegistry",
    "OverrideError",
    "PortNotFoundError",
    "UnknownModuleTypeError",
    "UnknownNumericalModelError",
]
