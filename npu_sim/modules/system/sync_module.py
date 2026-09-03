"""SYNC: Sync / Event Controller — barrier for multi-core. SPEC-010 §2."""

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


@ModuleRegistry.register
class SYNC(IModule):

    @classmethod
    def module_type(cls) -> str: return "SYNC"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "n_participants": {"type": "integer", "minimum": 2, "maximum": 16, "default": 2},
                "barrier_overhead_cycles": {"type": "integer", "minimum": 1, "default": 2},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("barrier", "Wait for N arrivals then release.", 4_000.0, 3.0, 1.0),
            Capability("semaphore", "Counted barrier.", 2_000.0, 1.5, 0.5),
            Capability("event_dispatch", "Broadcast release.", 2_000.0, 1.5, 0.5),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("arrive_in", PortDirection.INPUT, DataType.COMMAND, 64, 16),
            PortSpec("release_out", PortDirection.OUTPUT, DataType.COMMAND, 64, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._n_participants = 2; self._overhead = 2
        self._busy = False; self._stage = "idle"
        self._arrived_count = 0; self._barriers_released = 0
        self._arrive_port = None; self._release_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("SYNC.configure() once.")
        self._n_participants = config.get("n_participants", 2)
        self._overhead = config.get("barrier_overhead_cycles", 2)
        specs = {p.name: p for p in self.port_specs()}
        self._arrive_port = TlmInputPort(specs["arrive_in"], self._owner_id, self._clock)
        self._release_port = TlmOutputPort(specs["release_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"
    def destroy(self): self._arrive_port = self._release_port = None
    def input_ports(self): return {"arrive_in": self._arrive_port} if self._configured else {}
    def output_ports(self): return {"release_out": self._release_port} if self._release_port else {}
    def active_capabilities(self): return ["barrier", "semaphore", "event_dispatch"]
    def can_execute(self, op): return True

    def estimate_latency(self, op):
        c = self._overhead + 1
        return LatencyEstimate(c, c, c + 1, 0.9)

    def estimate_energy(self, op):
        return EnergyEstimate(1.0, self.static_power_uw()*1e-6, 0.9)

    def estimate_area(self):
        # §2.4: 8000 + n_participants × 1500
        area = 8_000.0 + self._n_participants * 1_500.0
        bd = {"core_barrier": 8_000.0, "per_participant_regs": self._n_participants * 1_500.0}
        return AreaModel(um2=area, breakdown=bd, notes="SPEC-010 §2.4 [calibration knob]")

    def total_area_um2(self): return self.estimate_area().um2

    @property
    def barriers_released(self) -> int: return self._barriers_released

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        """§2.3: collect n_participants arrives, then release_broadcast."""
        while True:
            self._busy = False; self._stage = "idle"
            tok = self._arrive_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "wait_arrive"
            self._arrived_count += 1
            yield
            if self._arrived_count >= self._n_participants:
                self._stage = "release_broadcast"
                for _ in range(self._overhead):
                    yield
                rel = TransportToken(
                    payload=None, size_bytes=8,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={"barrier_release": True, "barrier_id": self._barriers_released},
                )
                yield from self._release_port.send(rel)
                self._barriers_released += 1
                self._arrived_count = 0
