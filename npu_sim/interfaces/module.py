"""IModule and supporting dataclasses.

Reference: SPEC-001 §3.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.services import IEventBus, IStatSink
from npu_sim.interfaces.transport import ITransportPort, PortSpec


# Module type naming regex per SPEC-001 §3.1.1.
MODULE_TYPE_REGEX: re.Pattern[str] = re.compile(r"^[A-Z][A-Za-z0-9]{0,23}$")


@dataclass(frozen=True)
class Capability:
    """A declared capability of a module. Reference: SPEC-001 §3.1."""

    name: str
    description: str
    area_cost_um2: float
    static_power_uw: float
    dynamic_energy_pj: float
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleState:
    """Runtime state snapshot. Read-only, for debug / visualization.

    Reference: SPEC-001 §3.1.
    """

    busy: bool
    current_op: Optional[str] = None
    pipeline_occupancy: dict[str, float] = field(default_factory=dict)
    internal_fifo_levels: dict[str, int] = field(default_factory=dict)
    last_stall_reason: Optional[str] = None


@dataclass(frozen=True)
class LatencyEstimate:
    """Mapper-facing latency estimate. Reference: SPEC-001 §3.2."""

    min_cycles: int
    typical_cycles: int
    max_cycles: int
    confidence: float


@dataclass(frozen=True)
class EnergyEstimate:
    """Mapper-facing energy estimate. Reference: SPEC-001 §3.2."""

    dynamic_pj: float
    static_pj_per_cycle: float
    confidence: float


@dataclass(frozen=True)
class AreaModel:
    """Per-instance silicon area estimate. Reference: SPEC-001 v1.1 §3.2.5.

    Unlike LatencyEstimate / EnergyEstimate, area does not depend on op — it
    is a property of the configured module. Virtual modules (probes / test
    fixtures) may return ``um2=0.0`` with ``notes="virtual"``.
    """

    um2: float
    breakdown: dict[str, float] = field(default_factory=dict)
    notes: str = ""


class IModule(ABC):
    """Abstract base class for all NPU macro-modules.

    Reference: SPEC-001 §3.1.
    """

    # ============== Class-level metadata (no instantiation needed) ==============

    @classmethod
    @abstractmethod
    def module_type(cls) -> str:
        """Unique module type name. PascalCase, regex `^[A-Z][A-Za-z0-9]{0,23}$`.

        Reference: SPEC-001 §3.1.1.
        """

    @classmethod
    @abstractmethod
    def module_version(cls) -> str:
        """semver string. Reference: SPEC-001 §3.1."""

    @classmethod
    @abstractmethod
    def config_schema(cls) -> dict:
        """JSON Schema for the module's config dict. Reference: SPEC-001 §3.1."""

    @classmethod
    @abstractmethod
    def declared_capabilities(cls) -> list[Capability]:
        """All capabilities the module can support (whether active depends on config)."""

    @classmethod
    @abstractmethod
    def port_specs(cls) -> list[PortSpec]:
        """All port specs for this module type."""

    # ============== Lifecycle ==============

    @abstractmethod
    def bind_services(
        self,
        event_bus: IEventBus,
        stat_sink: IStatSink,
        clock: IClock,
    ) -> None:
        """Bind platform services. Called before configure()."""

    @abstractmethod
    def configure(self, config: dict) -> None:
        """Initialize from config dict. Called exactly once after bind_services."""

    @abstractmethod
    def reset(self) -> None:
        """Clear runtime state. Config preserved."""

    @abstractmethod
    def destroy(self) -> None:
        """Release resources."""

    # ============== Port access ==============

    @abstractmethod
    def input_ports(self) -> dict[str, ITransportPort]: ...

    @abstractmethod
    def output_ports(self) -> dict[str, ITransportPort]: ...

    # ============== Capability queries (Mapper API) ==============

    @abstractmethod
    def active_capabilities(self) -> list[str]: ...

    @abstractmethod
    def can_execute(self, operation: IOperation) -> bool: ...

    @abstractmethod
    def estimate_latency(self, operation: IOperation) -> LatencyEstimate: ...

    @abstractmethod
    def estimate_energy(self, operation: IOperation) -> EnergyEstimate: ...

    # ============== Runtime state ==============

    @abstractmethod
    def snapshot_state(self) -> ModuleState: ...

    # ============== Default-implemented area / power aggregation ==============

    def total_area_um2(self) -> float:
        """Sum of area_cost_um2 across active capabilities.

        Subclasses may override for shared-logic models. Reference: SPEC-001 §3.1.
        """
        active = set(self.active_capabilities())
        return sum(
            cap.area_cost_um2
            for cap in self.declared_capabilities()
            if cap.name in active
        )

    def estimate_area(self) -> AreaModel:
        """Per-instance area estimate. Reference: SPEC-001 v1.1 §3.2.5.

        Default implementation aggregates active capability area into a
        breakdown keyed by capability name. Subclasses may override to apply
        relocate / shared-logic / format-optimization adjustments.
        """
        active = set(self.active_capabilities())
        breakdown = {
            cap.name: cap.area_cost_um2
            for cap in self.declared_capabilities()
            if cap.name in active
        }
        return AreaModel(um2=sum(breakdown.values()), breakdown=breakdown)

    def static_power_uw(self) -> float:
        """Sum of static_power_uw across active capabilities."""
        active = set(self.active_capabilities())
        return sum(
            cap.static_power_uw
            for cap in self.declared_capabilities()
            if cap.name in active
        )
