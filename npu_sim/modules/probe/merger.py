"""Merger probe module: two inputs round-robin to one output.

Used by SPEC-002 §3.4 multi-producer contention tests. Reference: SPEC-001 §3.
"""

from __future__ import annotations

from typing import Iterator, Optional

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
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


@ModuleRegistry.register
class Merger(IModule):
    """Two INPUT ports + one OUTPUT port. Round-robins between in0 / in1."""

    @classmethod
    def module_type(cls) -> str:
        return "Merger"

    @classmethod
    def module_version(cls) -> str:
        return "0.1.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "forward_rate_cycles_per_token": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="merge",
                description="Round-robin merge two streams into one.",
                area_cost_um2=40.0,
                static_power_uw=0.4,
                dynamic_energy_pj=0.04,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("in0", PortDirection.INPUT, DataType.DATA, 64, fifo_depth=1),
            PortSpec("in1", PortDirection.INPUT, DataType.DATA, 64, fifo_depth=1),
            PortSpec("out", PortDirection.OUTPUT, DataType.DATA, 64, fifo_depth=1),
        ]

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._rate: int = 1
        self._forwarded: int = 0
        self._busy: bool = False
        self._in_ports: dict[str, TlmInputPort] = {}
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        self._rate = config.get("forward_rate_cycles_per_token", 1)
        for spec in self.port_specs():
            if spec.direction == PortDirection.INPUT:
                self._in_ports[spec.name] = TlmInputPort(spec, self._owner_id, self._clock)
            else:
                self._out_port = TlmOutputPort(spec, self._owner_id, self._clock, self._stat_sink)

    def reset(self) -> None:
        self._forwarded = 0
        self._busy = False

    def destroy(self) -> None:
        self._in_ports = {}
        self._out_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        return dict(self._in_ports)

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out": self._out_port} if self._out_port else {}

    def active_capabilities(self) -> list[str]:
        return ["merge"]

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset({"merge"})

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        cycles = n * self._rate
        return LatencyEstimate(min_cycles=cycles, typical_cycles=cycles, max_cycles=cycles, confidence=0.8)

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        return EnergyEstimate(dynamic_pj=0.04 * n, static_pj_per_cycle=4e-7, confidence=0.5)

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op="merge" if self._busy else None,
            internal_fifo_levels={
                name: p.fifo_level() for name, p in self._in_ports.items()
            },
        )

    @property
    def forwarded(self) -> int:
        return self._forwarded

    def behavior(self) -> Iterator[None]:
        """Fair round-robin: try the side `turn` first, then the other."""
        order = ["in0", "in1"]
        turn = 0
        while True:
            token = None
            for offset in range(len(order)):
                port = self._in_ports[order[(turn + offset) % len(order)]]
                token = port.try_receive()
                if token is not None:
                    break
            if token is None:
                self._busy = False
                yield
                continue
            self._busy = True
            yield from self._out_port.send(token)
            self._forwarded += 1
            turn = (turn + 1) % len(order)
            # Per-token forwarding cost.
            for _ in range(self._rate):
                yield
