"""TAU: Tensor Address Unit. Reference: SPEC-007 §4.

Generates burst-address streams for DMA. Independent module so that the
TAU+DMA-vs-MTU evaluation (§6.3) can compare two-module vs fused-module
topologies.
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.module import (
    AreaModel,
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
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


# §4.3.1: 4 cycles per burst address (calibration knob).
_CYCLES_PER_BURST = 4


@ModuleRegistry.register
class TAU(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "TAU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "addr_fifo_depth": {
                    "type": "integer", "minimum": 1, "maximum": 64, "default": 16,
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="tensor_address_gen",
                description="SPEC-007 §4.1.1: multi-dim tensor address generation.",
                area_cost_um2=30_000.0,
                static_power_uw=25.0,
                dynamic_energy_pj=_CYCLES_PER_BURST * 0.3,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="descriptor_in",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="addr_stream_out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=16,
            ),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type()
        self._configured = False
        self._addr_fifo_depth = 16
        self._bursts_per_token = 8
        self._busy = False
        self._stage = "idle"
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("TAU.configure() once only.")
        self._addr_fifo_depth = config.get("addr_fifo_depth", 16)
        self._bursts_per_token = config.get("bursts_per_token", 8)
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["descriptor_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["addr_stream_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None: self._busy = False
    def destroy(self) -> None:
        self._in_port = None
        self._out_port = None
    def input_ports(self) -> dict[str, ITransportPort]:
        return {"descriptor_in": self._in_port} if self._in_port else {}
    def output_ports(self) -> dict[str, ITransportPort]:
        return {"addr_stream_out": self._out_port} if self._out_port else {}

    def active_capabilities(self) -> list[str]:
        return ["tensor_address_gen"] if self._configured else []

    def can_execute(self, operation: IOperation) -> bool:
        return self._configured

    @staticmethod
    def _bursts(op: IOperation) -> int:
        return int(op.shape_info.get("bursts", 64))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        cycles = self._bursts(operation) * _CYCLES_PER_BURST
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=cycles,
            max_cycles=int(cycles * 1.2),
            confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 0.3,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        active = set(self.active_capabilities())
        breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in active
        }
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-007 §4.4.1 [calibration knob]",
        )

    def snapshot_state(self) -> ModuleState:
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        """§4.3.1: each descriptor token = (bursts × 4) cycles of address-gen.

        Stages visible in snapshot_state.current_op:
          load_descriptor (1 cycle) → addr_gen (bursts×4 cycles) → emit (1)
        """
        per_token = self._bursts_per_token * _CYCLES_PER_BURST
        while True:
            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue
            self._busy = True
            self._stage = "load_descriptor"
            yield
            self._stage = "addr_gen"
            for _ in range(max(0, per_token - 2)):  # -2 for load + emit
                yield
            self._stage = "emit"
            out = TransportToken(
                payload=token.payload,
                size_bytes=token.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "addressed_by": self._owner_id},
            )
            yield from self._out_port.send(out)
