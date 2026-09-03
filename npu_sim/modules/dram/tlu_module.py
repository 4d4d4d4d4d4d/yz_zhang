"""TLU: Tensor Lookup Unit / Embedding. SPEC-011 §4."""

from __future__ import annotations

import math
from typing import Iterator, Optional

from npu_sim import physical
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
class TLU(IModule):

    @classmethod
    def module_type(cls) -> str: return "TLU"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "table_size_kb": {"type": "integer", "minimum": 1, "default": 2048},
                "enable_scatter": {"type": "boolean", "default": False},
                "embedding_dim_bytes": {"type": "integer", "minimum": 1, "default": 256},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("embedding_lookup", "Index → vector.", 0.0, 0.0, 0.5),
            Capability("gather_op", "Batch gather.", 4_000.0, 2.0, 0.2),
            Capability("scatter_op", "Batch scatter.", 4_000.0, 2.0, 0.3),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("index_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("table_load", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("embedding_out", PortDirection.OUTPUT, DataType.DATA, 256, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._table_kb = 2048; self._enable_scatter = False; self._emb_dim = 256
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._looked_up = 0
        self._index_port = None; self._table_port = None; self._out_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("TLU.configure() once.")
        self._table_kb = config.get("table_size_kb", 2048)
        self._enable_scatter = config.get("enable_scatter", False)
        self._emb_dim = config.get("embedding_dim_bytes", 256)
        self._active_caps = ["embedding_lookup", "gather_op"]
        if self._enable_scatter:
            self._active_caps.append("scatter_op")
        specs = {p.name: p for p in self.port_specs()}
        self._index_port = TlmInputPort(specs["index_in"], self._owner_id, self._clock)
        self._table_port = TlmInputPort(specs["table_load"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["embedding_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._looked_up = 0
    def destroy(self): self._index_port = self._table_port = self._out_port = None
    def input_ports(self):
        return {"index_in": self._index_port, "table_load": self._table_port} if self._configured else {}
    def output_ports(self): return {"embedding_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        c = 1 + max(1, int(math.log2(max(2, self._table_kb))))
        return LatencyEstimate(c, c, c + 1, 0.8)

    def estimate_energy(self, op):
        # SPEC-013: reading one embedding vector = an eDRAM read of emb_dim
        # bytes (Horowitz SRAM read × eDRAM factor), replacing the flat 0.5 pJ.
        return EnergyEstimate(
            physical.edram_read_energy_pj(self._emb_dim),
            self.static_power_uw()*1e-6, 0.8,
        )

    def estimate_area(self):
        # SPEC-013: the multi-MB embedding table is on-chip eDRAM (1T1C,
        # ~3.7× denser than 6T SRAM), NOT SRAM density.
        storage = physical.embedding_table_area_um2(self._table_kb)
        cap_extra = sum(
            c.area_cost_um2 for c in self.declared_capabilities()
            if c.name in self._active_caps
        )
        return AreaModel(
            um2=storage + cap_extra,
            breakdown={"embedding_table": storage, "capabilities": cap_extra},
            notes=f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm eDRAM table",
        )

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        lookup_cycles = 1 + max(1, int(math.log2(max(2, self._table_kb))))
        while True:
            self._busy = False; self._stage = "idle"
            self._table_port.try_receive()  # opportunistic table fill
            req = self._index_port.try_receive()
            if req is None:
                yield; continue
            self._busy = True; self._stage = "decode_index"; yield
            self._stage = "table_read"
            for _ in range(lookup_cycles - 2):
                yield
            self._stage = "emit_embedding"
            out = TransportToken(
                payload=req.payload, size_bytes=self._emb_dim,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**req.metadata, "embedding": True},
            )
            yield from self._out_port.send(out)
            self._looked_up += 1
