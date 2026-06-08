"""DMA: Direct Memory Access. Reference: SPEC-007 §5."""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel,
    Capability,
    EnergyEstimate,
    IModule,
    LatencyEstimate,
    ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
    TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


# §5.3.1 calibration knobs.
_DRAM_BURST_LATENCY = 40
_BUS_WIDTH_BYTES = 32


@ModuleRegistry.register
class DMA(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "DMA"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "dram_burst_latency": {
                    "type": "integer", "minimum": 1, "default": _DRAM_BURST_LATENCY,
                },
                "bus_width_bytes": {
                    "type": "integer", "minimum": 1, "default": _BUS_WIDTH_BYTES,
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="bulk_memory_transfer",
                description="SPEC-007 §5.1.1: bulk DRAM ↔ on-chip transfer.",
                area_cost_um2=80_000.0,
                static_power_uw=60.0,
                dynamic_energy_pj=1.5,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("addr_stream_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type()
        self._configured = False
        self._burst_lat = _DRAM_BURST_LATENCY
        self._bus_w = _BUS_WIDTH_BYTES
        self._bursts_per_token = 8
        self._payload_per_token = 1024
        self._busy = False
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id): self._owner_id = module_id
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("DMA.configure() once only.")
        self._burst_lat = config.get("dram_burst_latency", _DRAM_BURST_LATENCY)
        self._bus_w = config.get("bus_width_bytes", _BUS_WIDTH_BYTES)
        self._bursts_per_token = config.get("bursts_per_token", 8)
        self._payload_per_token = config.get("payload_bytes_per_token", 1024)
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["addr_stream_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["data_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self): self._busy = False
    def destroy(self):
        self._in_port = None
        self._out_port = None
    def input_ports(self):
        return {"addr_stream_in": self._in_port} if self._in_port else {}
    def output_ports(self):
        return {"data_out": self._out_port} if self._out_port else {}

    def active_capabilities(self):
        return ["bulk_memory_transfer"] if self._configured else []

    def can_execute(self, operation): return self._configured

    @staticmethod
    def _bursts(op):
        return int(op.shape_info.get("bursts", 64))

    @staticmethod
    def _payload_bytes(op):
        return int(op.shape_info.get("payload_bytes", 4096))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        bursts = self._bursts(operation)
        payload = self._payload_bytes(operation)
        # §5.3.1: per-burst cost.
        per_burst = self._burst_lat + (payload // bursts) // self._bus_w
        cycles = bursts * per_burst
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.2), confidence=0.7,
        )

    def estimate_energy(self, operation):
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 1.5,
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
            um2=sum(breakdown.values()), breakdown=breakdown,
            notes="SPEC-007 §5.4.1 [calibration knob]",
        )

    def snapshot_state(self): return ModuleState(busy=self._busy)

    def _per_token_cycles(self) -> int:
        per_burst = self._burst_lat + (self._payload_per_token // self._bursts_per_token) // self._bus_w
        return self._bursts_per_token * per_burst

    def behavior(self) -> Iterator[None]:
        """§5.3.1: each address stream token = (bursts × per_burst) cycles."""
        per_token = self._per_token_cycles()
        while True:
            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                yield
                continue
            self._busy = True
            for _ in range(per_token):
                yield
            out = TransportToken(
                payload=token.payload,
                size_bytes=self._payload_per_token,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "transferred_by": self._owner_id},
            )
            yield from self._out_port.send(out)
