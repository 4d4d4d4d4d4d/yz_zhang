"""L2: Last-Level Cache. SPEC-011 §2."""

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
class L2(IModule):

    @classmethod
    def module_type(cls) -> str: return "L2"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "capacity_kb": {"type": "integer", "minimum": 16, "maximum": 16_384, "default": 512},
                "hit_cycles": {"type": "integer", "minimum": 1, "default": 8},
                "miss_cycles": {"type": "integer", "minimum": 1, "default": 12},
                "hit_rate": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.8},
                "enable_prefetch": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("cache_read", "L2 read.", 0.0, 0.0, 1.2),
            Capability("cache_write", "L2 write.", 0.0, 0.0, 1.5),
            Capability("writeback_dirty", "Dirty line writeback.", 4_000.0, 2.0, 0.5),
            Capability("prefetch_stride", "Stride prefetcher.", 8_000.0, 4.0, 0.3),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("req_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("data_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 16),
            PortSpec("mc_pass_through", PortDirection.OUTPUT, DataType.COMMAND, 64, 8),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._capacity_kb = 512; self._hit_c = 8; self._miss_c = 12
        self._hit_rate = 0.8; self._enable_prefetch = False
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"
        self._hits = 0; self._misses = 0
        self._rng = random.Random(0xC0FFEE)
        self._req_port = None; self._data_port = None
        self._out_port = None; self._mc_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("L2.configure() once.")
        self._capacity_kb = config.get("capacity_kb", 512)
        self._hit_c = config.get("hit_cycles", 8)
        self._miss_c = config.get("miss_cycles", 12)
        self._hit_rate = config.get("hit_rate", 0.8)
        self._enable_prefetch = config.get("enable_prefetch", False)
        self._active_caps = ["cache_read", "cache_write", "writeback_dirty"]
        if self._enable_prefetch:
            self._active_caps.append("prefetch_stride")
        specs = {p.name: p for p in self.port_specs()}
        self._req_port = TlmInputPort(specs["req_in"], self._owner_id, self._clock)
        self._data_port = TlmInputPort(specs["data_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["data_out"], self._owner_id, self._clock, self._stat_sink)
        self._mc_port = TlmOutputPort(specs["mc_pass_through"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self):
        self._busy = False; self._stage = "idle"
        self._hits = self._misses = 0
        self._rng = random.Random(0xC0FFEE)
    def destroy(self): self._req_port = self._data_port = self._out_port = self._mc_port = None
    def input_ports(self):
        return {"req_in": self._req_port, "data_in": self._data_port} if self._configured else {}
    def output_ports(self):
        return {"data_out": self._out_port, "mc_pass_through": self._mc_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        # Weighted by hit_rate.
        avg = self._hit_c * self._hit_rate + self._miss_c * (1 - self._hit_rate)
        c = int(round(avg))
        return LatencyEstimate(self._hit_c, c, self._miss_c, 0.8)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("payload_bytes", 256))
        return EnergyEstimate(1.2 * n, self.static_power_uw()*1e-6, 0.8)

    def estimate_area(self):
        storage = self._capacity_kb * 800.0
        cap_extra = sum(
            c.area_cost_um2 for c in self.declared_capabilities()
            if c.name in self._active_caps
        )
        return AreaModel(
            um2=storage + cap_extra,
            breakdown={"l2_storage": storage, "capabilities": cap_extra},
            notes="SPEC-011 §2.4 [calibration knob]",
        )

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def hit_count(self) -> int: return self._hits
    @property
    def miss_count(self) -> int: return self._misses

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            self._data_port.try_receive()  # passive sink for writebacks
            req = self._req_port.try_receive()
            if req is None:
                yield; continue
            self._busy = True; self._stage = "lookup"; yield
            # Hit/miss decision: static random per hit_rate.
            if self._rng.random() < self._hit_rate:
                self._stage = "hit_serve"
                for _ in range(self._hit_c - 1):
                    yield
                self._hits += 1
            else:
                self._stage = "miss_pass"
                for _ in range(self._miss_c - 1):
                    yield
                self._misses += 1

            out = TransportToken(
                payload=req.payload, size_bytes=int(req.metadata.get("bytes", 64)),
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**req.metadata, "l2_served": True},
            )
            yield from self._out_port.send(out)
