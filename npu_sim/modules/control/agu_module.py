"""AGU: Address Generation Unit. Reference: SPEC-007 §7.

Provides inner-loop addresses to a MAC or DSB client. The "MAC/DSB/AGU
算法激励" evaluation (§7.3.2) is exercised by varying
agu_pipeline_depth + client array size in the use-case test, surfacing
the stall behavior.
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.errors import ConfigurationError
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


@ModuleRegistry.register
class AGU(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "AGU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "client_module_id": {
                    "type": "string",
                    "description": "SPEC-007 §7.1.2: required (MAC or DSB peer).",
                },
                "agu_pipeline_depth": {
                    "type": "integer", "minimum": 1, "maximum": 8, "default": 3,
                },
            },
            "required": ["client_module_id"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="inner_loop_address_gen",
                description="SPEC-007 §7.1.1: per-cycle inner-loop addr generation.",
                area_cost_um2=15_000.0,
                static_power_uw=12.0,
                dynamic_energy_pj=0.4,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("op_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("tick_in", PortDirection.INPUT, DataType.COMMAND, 8, 4),
            PortSpec("inner_addr_out", PortDirection.OUTPUT, DataType.COMMAND, 64, 8),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type()
        self._configured = False
        self._client_id = None
        self._pipeline_depth = 3
        self._addresses_per_token = 64
        self._busy = False
        self._stage = "idle"
        self._first_token = True
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id): self._owner_id = module_id
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("AGU.configure() once only.")
        if "client_module_id" not in config or not config["client_module_id"]:
            raise ConfigurationError(
                "AGU.configure(): SPEC-007 §7.1.2 requires client_module_id."
            )
        self._client_id = config["client_module_id"]
        self._pipeline_depth = config.get("agu_pipeline_depth", 3)
        self._addresses_per_token = config.get("addresses_per_token", 64)
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["op_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["inner_addr_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self):
        self._busy = False
        self._first_token = True
    def destroy(self):
        self._in_port = None
        self._out_port = None
    def input_ports(self):
        return {"op_in": self._in_port} if self._in_port else {}
    def output_ports(self):
        return {"inner_addr_out": self._out_port} if self._out_port else {}

    def active_capabilities(self):
        return ["inner_loop_address_gen"] if self._configured else []

    def can_execute(self, operation): return self._configured

    @property
    def pipeline_depth(self) -> int:
        return self._pipeline_depth

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # §7.3.1: 1 address/cycle steady-state; pipeline_depth is fill cost.
        n_addrs = int(operation.shape_info.get("n_addresses", 256))
        cycles = self._pipeline_depth + n_addrs  # fill + steady throughput.
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.1), confidence=0.8,
        )

    def estimate_energy(self, operation):
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 0.4,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.8,
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
            notes="SPEC-007 §7.4.1 [calibration knob]",
        )

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        """§7.3.1: 1 addr/cycle steady-state; pipeline_depth fills only on
        first token (or after idle gap). Stages: fill / addr_stream / emit.
        """
        n_addrs = self._addresses_per_token
        while True:
            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                self._stage = "idle"
                self._first_token = True  # resumes fill cost after idle
                yield
                continue
            self._busy = True
            if self._first_token:
                self._stage = "fill"
                for _ in range(self._pipeline_depth - 1):
                    yield
                self._first_token = False
            self._stage = "addr_stream"
            for _ in range(n_addrs):
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

    def estimate_stall_to_client(self, client_throughput_per_cycle: float = 1.0) -> int:
        """SPEC-007 §7.3.1: AGU must deliver 1 addr/cycle; if pipeline_depth
        exceeds 1, fill phase stalls the client by (depth - 1) cycles.
        Used by §7 use-case to assert stimulus behavior.
        """
        return max(0, self._pipeline_depth - 1)
