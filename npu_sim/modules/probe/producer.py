"""Producer probe module: emits N tokens at a configurable rate.

Used by SPEC-002 §6 backpressure tests. Reference: SPEC-001 §3, SPEC-002 §3.2.
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
from npu_sim.runtime.ports import TlmOutputPort


@ModuleRegistry.register
class Producer(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "Producer"

    @classmethod
    def module_version(cls) -> str:
        return "0.1.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "n_tokens": {"type": "integer", "minimum": 0, "default": 16},
                "send_rate_cycles_per_token": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                },
                "payload_size_bytes": {"type": "integer", "minimum": 1, "default": 8},
            },
            "required": ["n_tokens"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="emit",
                description="Generate tokens at a fixed rate.",
                area_cost_um2=10.0,
                static_power_uw=0.1,
                dynamic_energy_pj=0.01,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="out",
                direction=PortDirection.OUTPUT,
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
        self._n_tokens: int = 0
        self._rate: int = 1
        self._payload_size: int = 8
        self._sent: int = 0
        self._busy: bool = False
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        """Tests / Elaborator helper to set a stable instance id used as owner_module."""
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        self._n_tokens = config["n_tokens"]
        self._rate = config.get("send_rate_cycles_per_token", 1)
        self._payload_size = config.get("payload_size_bytes", 8)
        # Create the TLM port now that we know clock + stat_sink.
        out_spec = next(p for p in self.port_specs() if p.name == "out")
        self._out_port = TlmOutputPort(
            port_spec=out_spec,
            owner_module_id=self._owner_id,
            clock=self._clock,
            stat_sink=self._stat_sink,
        )

    def reset(self) -> None:
        self._sent = 0
        self._busy = False

    def destroy(self) -> None:
        self._out_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        return {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out": self._out_port} if self._out_port else {}

    def active_capabilities(self) -> list[str]:
        return ["emit"]

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset({"emit"})

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", self._n_tokens)
        cycles = n * self._rate
        return LatencyEstimate(min_cycles=cycles, typical_cycles=cycles, max_cycles=cycles, confidence=0.9)

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", self._n_tokens)
        return EnergyEstimate(dynamic_pj=0.01 * n, static_pj_per_cycle=1e-7, confidence=0.5)

    def snapshot_state(self) -> ModuleState:
        return ModuleState(busy=self._busy, current_op="emit" if self._busy else None)

    # ============== behavior (generator) ==============

    def behavior(self) -> Iterator[None]:
        """Send n_tokens tokens, one every `send_rate_cycles_per_token` cycles.

        Stall events are emitted automatically by `TlmOutputPort.send()` when
        the downstream FIFO is full.
        """
        for i in range(self._n_tokens):
            self._busy = True
            token = TransportToken(
                payload=bytes(self._payload_size),
                size_bytes=self._payload_size,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={"seq": i},
            )
            yield from self._out_port.send(token)  # blocking send (generator)
            self._sent += 1
            # One mandatory cycle per token + (rate - 1) idle cycles.
            for _ in range(self._rate):
                yield
        self._busy = False
