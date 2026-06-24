"""NoC: Network-on-Chip / Crossbar. SPEC-009 §3.

Fixed 4×4 (4 in ports, 4 out ports) in v1.0. Multi-tile traffic routes
through this single XBAR; arbitration serializes collisions.
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel, Capability, EnergyEstimate, IModule, LatencyEstimate, ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.transport import (
    DataType, ITransportPort, PortDirection, PortSpec, TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


_N_PORTS = 4


@ModuleRegistry.register
class NoC(IModule):

    @classmethod
    def module_type(cls) -> str: return "NoC"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "route_cycles": {"type": "integer", "minimum": 1, "default": 2},
                "enable_multicast": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("xbar_route", "Static crossbar route.", 128_000.0, 60.0, 0.8),
            Capability("multicast", "1-to-N copy.", 16_000.0, 8.0, 0.4),
            Capability("packet_arbitration", "Collision arbitration.", 8_000.0, 4.0, 0.2),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        specs = []
        for i in range(_N_PORTS):
            specs.append(PortSpec(f"port_{i}_in", PortDirection.INPUT, DataType.DATA, 256, 4))
            specs.append(PortSpec(f"port_{i}_out", PortDirection.OUTPUT, DataType.DATA, 256, 4))
        return specs

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._route_cycles = 2; self._enable_multicast = False
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._routed = 0
        self._in_ports: dict[str, TlmInputPort] = {}
        self._out_ports: dict[str, TlmOutputPort] = {}

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("NoC.configure() once.")
        self._route_cycles = config.get("route_cycles", 2)
        self._enable_multicast = config.get("enable_multicast", False)
        self._active_caps = ["xbar_route", "packet_arbitration"]
        if self._enable_multicast:
            self._active_caps.append("multicast")
        specs = {p.name: p for p in self.port_specs()}
        for i in range(_N_PORTS):
            self._in_ports[f"port_{i}_in"] = TlmInputPort(
                specs[f"port_{i}_in"], self._owner_id, self._clock)
            self._out_ports[f"port_{i}_out"] = TlmOutputPort(
                specs[f"port_{i}_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._routed = 0
    def destroy(self): self._in_ports = {}; self._out_ports = {}
    def input_ports(self): return dict(self._in_ports)
    def output_ports(self): return dict(self._out_ports)
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        return LatencyEstimate(self._route_cycles, self._route_cycles, self._route_cycles + 1, 0.8)

    def estimate_energy(self, op):
        return EnergyEstimate(0.8, self.static_power_uw()*1e-6, 0.8)

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        """Round-robin scan input ports; each packet routes to port (i+1) % N_PORTS by default.
        Token metadata may specify 'dst_port' for explicit routing.
        """
        while True:
            self._busy = False; self._stage = "idle"
            routed_this_cycle = False
            for i in range(_N_PORTS):
                in_port = self._in_ports[f"port_{i}_in"]
                tok = in_port.try_receive()
                if tok is None:
                    continue
                dst = int(tok.metadata.get("dst_port", (i + 1) % _N_PORTS))
                self._busy = True; self._stage = f"route_in_{i}"
                for _ in range(self._route_cycles):
                    yield
                self._stage = f"emit_out_{dst}"
                out_tok = TransportToken(
                    payload=tok.payload, size_bytes=tok.size_bytes,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={**tok.metadata, "routed_by": self._owner_id, "via": f"in{i}→out{dst}"},
                )
                yield from self._out_ports[f"port_{dst}_out"].send(out_tok)
                self._routed += 1
                routed_this_cycle = True
                break  # process one packet per round
            if not routed_this_cycle:
                yield
