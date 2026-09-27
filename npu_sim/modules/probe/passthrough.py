"""Passthrough probe module: forwards each received token to its output.

Used as the middle node in 3-module backpressure-chain tests.
Reference: SPEC-001 §3, SPEC-002 §6.4.
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
class Passthrough(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "Passthrough"

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
                name="forward",
                description="Receive a token and forward it unchanged.",
                area_cost_um2=20.0,
                static_power_uw=0.2,
                dynamic_energy_pj=0.02,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="in",
                direction=PortDirection.INPUT,
                data_type=DataType.DATA,
                width_bits=64,
                fifo_depth=1,
            ),
            PortSpec(
                name="out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.DATA,
                width_bits=64,
                fifo_depth=1,
            ),
        ]

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._rate: int = 1
        self._forwarded: int = 0
        self._busy: bool = False
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        self._rate = config.get("forward_rate_cycles_per_token", 1)
        in_spec = next(p for p in self.port_specs() if p.name == "in")
        out_spec = next(p for p in self.port_specs() if p.name == "out")
        self._in_port = TlmInputPort(in_spec, self._owner_id, self._clock)
        self._out_port = TlmOutputPort(out_spec, self._owner_id, self._clock, self._stat_sink)

    def reset(self) -> None:
        self._forwarded = 0
        self._busy = False

    def destroy(self) -> None:
        self._in_port = None
        self._out_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        return {"in": self._in_port} if self._in_port else {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out": self._out_port} if self._out_port else {}

    def active_capabilities(self) -> list[str]:
        return ["forward"]

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset({"forward"})

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        cycles = n * self._rate
        return LatencyEstimate(min_cycles=cycles, typical_cycles=cycles, max_cycles=cycles, confidence=0.9)

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        return EnergyEstimate(dynamic_pj=0.02 * n, static_pj_per_cycle=2e-7, confidence=0.5)

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op="forward" if self._busy else None,
            internal_fifo_levels={"in": self._in_port.fifo_level() if self._in_port else 0},
        )

    @property
    def forwarded(self) -> int:
        return self._forwarded

    def behavior(self) -> Iterator[None]:
        while True:
            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                yield
                continue
            self._busy = True
            yield from self._out_port.send(token)
            self._forwarded += 1
            # Mandatory cycle per token + optional extra idle.
            for _ in range(self._rate):
                yield
