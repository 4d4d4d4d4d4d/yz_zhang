"""MMU: Memory Management Unit (virtual → physical address). SPEC-011 §6."""

from __future__ import annotations

import random
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


@ModuleRegistry.register
class MMU(IModule):

    @classmethod
    def module_type(cls) -> str: return "MMU"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "tlb_entries": {"type": "integer", "minimum": 1, "maximum": 1024, "default": 64},
                "tlb_hit_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.95},
                "pt_walk_cycles": {"type": "integer", "minimum": 1, "default": 20},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("virtual_address_translate", "VA → PA.", 8_000.0, 4.0, 0.1),
            Capability("tlb_lookup", "TLB CAM lookup.", 0.0, 0.0, 0.05),
            Capability("page_table_walk", "Multi-level PT walk.", 4_000.0, 2.0, 0.3),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("vaddr_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("paddr_out", PortDirection.OUTPUT, DataType.COMMAND, 64, 16),
            PortSpec("pt_walk_req", PortDirection.OUTPUT, DataType.COMMAND, 64, 4),
            PortSpec("pt_walk_resp", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._tlb_entries = 64; self._hit_rate = 0.95; self._walk_cycles = 20
        self._busy = False; self._stage = "idle"
        self._hits = 0; self._misses = 0
        self._rng = random.Random(0xBEEF)
        self._vaddr_port = None; self._paddr_port = None
        self._walk_req_port = None; self._walk_resp_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("MMU.configure() once.")
        self._tlb_entries = config.get("tlb_entries", 64)
        self._hit_rate = config.get("tlb_hit_rate", 0.95)
        self._walk_cycles = config.get("pt_walk_cycles", 20)
        specs = {p.name: p for p in self.port_specs()}
        self._vaddr_port = TlmInputPort(specs["vaddr_in"], self._owner_id, self._clock)
        self._paddr_port = TlmOutputPort(specs["paddr_out"], self._owner_id, self._clock, self._stat_sink)
        self._walk_req_port = TlmOutputPort(specs["pt_walk_req"], self._owner_id, self._clock, self._stat_sink)
        self._walk_resp_port = TlmInputPort(specs["pt_walk_resp"], self._owner_id, self._clock)
        self._configured = True

    def reset(self):
        self._busy = False; self._stage = "idle"
        self._hits = self._misses = 0
        self._rng = random.Random(0xBEEF)
    def destroy(self):
        self._vaddr_port = self._paddr_port = None
        self._walk_req_port = self._walk_resp_port = None
    def input_ports(self):
        if not self._configured: return {}
        return {"vaddr_in": self._vaddr_port, "pt_walk_resp": self._walk_resp_port}
    def output_ports(self):
        if not self._paddr_port: return {}
        return {"paddr_out": self._paddr_port, "pt_walk_req": self._walk_req_port}
    def active_capabilities(self):
        return ["virtual_address_translate", "tlb_lookup", "page_table_walk"]
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        avg = 1 * self._hit_rate + (1 + self._walk_cycles) * (1 - self._hit_rate)
        return LatencyEstimate(1, int(round(avg)), 1 + self._walk_cycles, 0.8)

    def estimate_energy(self, op):
        return EnergyEstimate(0.1, self.static_power_uw()*1e-6, 0.8)

    def estimate_area(self):
        area = self._tlb_entries * 200.0 + 8_000.0
        return AreaModel(
            um2=area,
            breakdown={"tlb_cam": self._tlb_entries * 200.0, "walker_logic": 8_000.0},
            notes="SPEC-011 §6.4 [calibration knob]",
        )

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def tlb_hits(self) -> int: return self._hits
    @property
    def tlb_misses(self) -> int: return self._misses

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            req = self._vaddr_port.try_receive()
            if req is None:
                yield; continue
            self._busy = True; self._stage = "tlb_lookup"; yield
            if self._rng.random() < self._hit_rate:
                self._stage = "tlb_hit"
                self._hits += 1
            else:
                self._stage = "tlb_miss_walk"
                for _ in range(self._walk_cycles):
                    yield
                self._misses += 1
            self._stage = "emit_paddr"
            out = TransportToken(
                payload=req.payload, size_bytes=8,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**req.metadata, "translated": True},
            )
            yield from self._paddr_port.send(out)
