"""MC: Memory Controller (HBM/DDR). SPEC-011 §1."""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel, Capability, EnergyEstimate, IModule, LatencyEstimate, ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.services import StallReason
from npu_sim.interfaces.transport import (
    DataType, ITransportPort, PortDirection, PortSpec, TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


@ModuleRegistry.register
class MC(IModule):

    @classmethod
    def module_type(cls) -> str: return "MC"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "n_banks": {"type": "integer", "minimum": 1, "maximum": 32, "default": 8},
                "row_hit_cycles": {"type": "integer", "minimum": 1, "default": 4},
                "row_miss_cycles": {"type": "integer", "minimum": 1, "default": 40},
                "refresh_period_cycles": {"type": "integer", "minimum": 100, "default": 7800},
                "refresh_overhead_cycles": {"type": "integer", "minimum": 1, "default": 30},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("dram_read", "Read from DRAM bank.", 50_000.0, 30.0, 5.0),
            Capability("dram_write", "Write to DRAM bank.", 0.0, 0.0, 8.0),
            Capability("refresh", "Periodic refresh.", 4_000.0, 4.0, 0.5),
            Capability("row_buffer_hit_track", "Open-row tracking.", 4_000.0, 3.0, 0.2),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("req_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("writeback_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._n_banks = 8; self._row_hit = 4; self._row_miss = 40
        self._refresh_period = 7800; self._refresh_overhead = 30
        self._open_row = None
        self._busy = False; self._stage = "idle"
        self._cycle_count = 0; self._served = 0
        self._req_port = None; self._wb_port = None; self._out_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("MC.configure() once.")
        self._n_banks = config.get("n_banks", 8)
        self._row_hit = config.get("row_hit_cycles", 4)
        self._row_miss = config.get("row_miss_cycles", 40)
        self._refresh_period = config.get("refresh_period_cycles", 7800)
        self._refresh_overhead = config.get("refresh_overhead_cycles", 30)
        specs = {p.name: p for p in self.port_specs()}
        self._req_port = TlmInputPort(specs["req_in"], self._owner_id, self._clock)
        self._wb_port = TlmInputPort(specs["writeback_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["data_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self):
        self._busy = False; self._stage = "idle"; self._cycle_count = 0; self._served = 0
        self._open_row = None
    def destroy(self): self._req_port = self._wb_port = self._out_port = None
    def input_ports(self):
        return {"req_in": self._req_port, "writeback_in": self._wb_port} if self._configured else {}
    def output_ports(self): return {"data_out": self._out_port} if self._out_port else {}
    def active_capabilities(self):
        return ["dram_read", "dram_write", "refresh", "row_buffer_hit_track"]
    def can_execute(self, op): return True

    def estimate_latency(self, op):
        return LatencyEstimate(self._row_hit, self._row_miss, self._row_miss + 10, 0.7)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("payload_bytes", 64))
        return EnergyEstimate(5.0 * n, self.static_power_uw()*1e-6, 0.7)

    def estimate_area(self):
        area = 50_000.0 + self._n_banks * 8_000.0
        return AreaModel(um2=area, breakdown={"banks": area}, notes="SPEC-011 §1.4 [calibration knob]")

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def served(self) -> int: return self._served

    def behavior(self) -> Iterator[None]:
        while True:
            self._cycle_count += 1
            # Periodic refresh.
            if self._cycle_count % self._refresh_period == 0:
                self._busy = True; self._stage = "refresh"
                for _ in range(self._refresh_overhead):
                    yield
                self._open_row = None
                continue

            self._busy = False; self._stage = "idle"
            req = self._req_port.try_receive()
            if req is None:
                yield; continue

            self._busy = True
            row_key = req.metadata.get("row", 0)
            if row_key == self._open_row:
                self._stage = "column_access"
                for _ in range(self._row_hit):
                    yield
            else:
                self._stage = "row_open"
                for _ in range(self._row_miss):
                    yield
                self._open_row = row_key

            self._stage = "emit_data"
            out = TransportToken(
                payload=req.payload,
                size_bytes=int(req.metadata.get("bytes", 64)),
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**req.metadata, "from_mc": True},
            )
            yield from self._out_port.send(out)
            self._served += 1
