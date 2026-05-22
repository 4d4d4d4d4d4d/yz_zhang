"""Platform-wide exception types.

Reference: implements error types referenced across SPEC-001..004.
"""


class NpuSimError(Exception):
    """Base for all platform errors."""


class DuplicateModuleTypeError(NpuSimError):
    """Raised by ModuleRegistry when a module_type is registered twice.

    Reference: SPEC-001 §3.1.1, §4.
    """


class UnknownModuleTypeError(NpuSimError):
    """Raised by ModuleRegistry.create when module_type is not registered.

    Reference: SPEC-001 §4.
    """


class InvalidModuleTypeNameError(NpuSimError):
    """Raised when module_type() return value violates the naming regex.

    Reference: SPEC-001 §3.1.1.
    """


class DuplicateNumericalModelError(NpuSimError):
    """Raised by NumericalModelRegistry for duplicate (module_type, fidelity).

    Reference: SPEC-004 §3.3.
    """


class UnknownNumericalModelError(NpuSimError):
    """Raised by NumericalModelRegistry.create when key not found and no fallback.

    Reference: SPEC-004 §3.3.
    """


class InvalidStallReport(NpuSimError):
    """Raised by IStatSink when record_stall violates the legality table.

    Reference: SPEC-002 §3.5.
    """


class MapperBugError(NpuSimError):
    """Raised when a stall reason indicates the Mapper produced an invalid route.

    Reference: SPEC-002 §4.1 CAPABILITY_MISSING / SPEC-003 §3.4 mapping_hints.
    """


class InvalidMappingHintError(NpuSimError):
    """Raised when mapping_hints points to a module that cannot execute the op.

    Reference: SPEC-003 §3.4.
    """


class OverrideError(NpuSimError):
    """Raised by Elaborator when DSL overrides are inconsistent.

    Covers: missing-module override targets, chain inheritance, add_connections
    referencing removed modules.

    Reference: SPEC-003 §5, §6.
    """


class PortNotFoundError(NpuSimError):
    """Raised by Elaborator when a connection references a non-existent port.

    Reference: SPEC-003 §5 Phase 3.
    """


class CircularReferenceError(NpuSimError):
    """Raised by Elaborator when clock domain references form a cycle.

    Reference: SPEC-003 §7 (test).
    """
