"""Dummy module: minimal IModule used by platform self-tests.

The module pretends to support a no-op "passthrough" capability.
It does not implement real port objects yet (Phase 1 scope: contracts and
registration); pipeline / FIFO wiring lands in Phase 2.

Reference: SPEC-001 §5 (DAGC example), SPEC-001 §6 (test template).
"""

from __future__ import annotations

from typing import Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.module import (
    Capability,
    EnergyEstimate,
    IModule,
    LatencyEstimate,
    ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.services import IEventBus, IStatSink
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
)


@ModuleRegistry.register
class Dummy(IModule):
    """No-op module used for framework self-test."""

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "Dummy"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "throughput_elems_per_cycle": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 64,
                    "default": 1,
                },
                "support_extra": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable the optional 'extra' capability.",
                },
                "internal_fifo_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 256,
                    "default": 8,
                },
            },
            "required": ["throughput_elems_per_cycle"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="passthrough",
                description="Forward inputs unchanged to outputs.",
                area_cost_um2=100.0,
                static_power_uw=1.0,
                dynamic_energy_pj=0.1,
            ),
            Capability(
                name="extra",
                description="Optional auxiliary capability gated by config flag.",
                area_cost_um2=50.0,
                static_power_uw=0.5,
                dynamic_energy_pj=0.05,
                depends_on=("passthrough",),
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="in_data",
                direction=PortDirection.INPUT,
                data_type=DataType.DATA,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="out_data",
                direction=PortDirection.OUTPUT,
                data_type=DataType.DATA,
                width_bits=64,
                fifo_depth=4,
            ),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._throughput: int = 1
        self._support_extra: bool = False
        self._internal_fifo_depth: int = 8
        self._active_caps: list[str] = []
        self._busy: bool = False
        self._current_op: Optional[str] = None

    def bind_services(
        self,
        event_bus: IEventBus,
        stat_sink: IStatSink,
        clock: IClock,
    ) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("Dummy.configure() can only be called once.")
        self._throughput = config["throughput_elems_per_cycle"]
        self._support_extra = config.get("support_extra", False)
        self._internal_fifo_depth = config.get("internal_fifo_depth", 8)

        self._active_caps = ["passthrough"]
        if self._support_extra:
            self._active_caps.append("extra")

        self._configured = True

    def reset(self) -> None:
        self._busy = False
        self._current_op = None

    def destroy(self) -> None:
        self._event_bus = None
        self._stat_sink = None
        self._clock = None

    # ============== Ports ==============
    # Phase 1: real port objects not yet implemented; placeholders return {}.

    def input_ports(self) -> dict[str, ITransportPort]:
        return {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        required = set(operation.required_capabilities)
        return required.issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 1)
        cycles = max(1, n // self._throughput)
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=cycles,
            max_cycles=cycles * 2,
            confidence=0.5,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 1)
        # Simple per-element energy model: passthrough energy * n.
        per_elem_pj = next(
            (c.dynamic_energy_pj for c in self.declared_capabilities() if c.name == "passthrough"),
            0.0,
        )
        return EnergyEstimate(
            dynamic_pj=per_elem_pj * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.5,
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._current_op,
            pipeline_occupancy={},
            internal_fifo_levels={},
            last_stall_reason=None,
        )
