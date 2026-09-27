"""Consumer probe module: receives tokens at a configurable rate.

Used by SPEC-002 §6 backpressure tests. Reference: SPEC-001 §3.
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
    TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort


@ModuleRegistry.register
class Consumer(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "Consumer"

    @classmethod
    def module_version(cls) -> str:
        return "0.1.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "receive_rate_cycles_per_token": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                },
                "max_to_accept": {
                    "type": "integer",
                    "minimum": -1,
                    "default": -1,
                    "description": "Stop after N tokens; -1 means accept forever.",
                },
                "never_consume": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, never drain the FIFO — used to test "
                                   "upstream backpressure propagation.",
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="absorb",
                description="Receive tokens at a fixed rate.",
                area_cost_um2=10.0,
                static_power_uw=0.1,
                dynamic_energy_pj=0.01,
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
        ]

    # ============== state ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._rate: int = 1
        self._max: int = -1
        self._never: bool = False
        self._received: int = 0
        self._busy: bool = False
        self._received_tokens: list[TransportToken] = []
        self._in_port: Optional[TlmInputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        self._rate = config.get("receive_rate_cycles_per_token", 1)
        self._max = config.get("max_to_accept", -1)
        self._never = config.get("never_consume", False)
        in_spec = next(p for p in self.port_specs() if p.name == "in")
        self._in_port = TlmInputPort(
            port_spec=in_spec,
            owner_module_id=self._owner_id,
            clock=self._clock,
        )

    def reset(self) -> None:
        self._received = 0
        self._received_tokens.clear()
        self._busy = False

    def destroy(self) -> None:
        self._in_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        return {"in": self._in_port} if self._in_port else {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {}

    def active_capabilities(self) -> list[str]:
        return ["absorb"]

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset({"absorb"})

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        cycles = n * self._rate
        return LatencyEstimate(min_cycles=cycles, typical_cycles=cycles, max_cycles=cycles, confidence=0.9)

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        return EnergyEstimate(dynamic_pj=0.01 * n, static_pj_per_cycle=1e-7, confidence=0.5)

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op="absorb" if self._busy else None,
            internal_fifo_levels={"in": self._in_port.fifo_level() if self._in_port else 0},
        )

    # ============== queries used by tests ==============

    @property
    def received(self) -> int:
        return self._received

    @property
    def received_tokens(self) -> list[TransportToken]:
        return list(self._received_tokens)

    # ============== behavior (generator) ==============

    def behavior(self) -> Iterator[None]:
        """Drain the input port. Records nothing to stat_sink — backpressure on
        the upstream side is recorded by the upstream's output port automatically.
        """
        while True:
            if self._max >= 0 and self._received >= self._max:
                self._busy = False
                return
            if self._never:
                # Park forever; do not call try_receive.
                self._busy = False
                yield
                continue

            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                yield  # nothing to consume right now; wait
                continue

            # Got a token: "process" it for `rate` cycles.
            self._busy = True
            self._received_tokens.append(token)
            self._received += 1
            for _ in range(self._rate):
                yield
