"""CMDQ: Command Queue (host → MCU buffer). SPEC-011 §5."""

from __future__ import annotations

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
class CMDQ(IModule):

    @classmethod
    def module_type(cls) -> str: return "CMDQ"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "queue_depth": {"type": "integer", "minimum": 1, "maximum": 4096, "default": 64},
                "enable_priority": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("fifo_queue", "FIFO ordering.", 0.0, 0.5, 0.05),
            Capability("priority_queue", "Priority ordering.", 5_000.0, 2.0, 0.1),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("host_in", PortDirection.INPUT, DataType.COMMAND, 64, 32),
            PortSpec("mcu_out", PortDirection.OUTPUT, DataType.COMMAND, 64, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._depth = 64; self._enable_priority = False
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"
        self._enqueued = 0; self._dequeued = 0
        self._host_port = None; self._mcu_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("CMDQ.configure() once.")
        self._depth = config.get("queue_depth", 64)
        self._enable_priority = config.get("enable_priority", False)
        self._active_caps = ["fifo_queue"]
        if self._enable_priority:
            self._active_caps.append("priority_queue")
        specs = {p.name: p for p in self.port_specs()}
        self._host_port = TlmInputPort(specs["host_in"], self._owner_id, self._clock)
        self._mcu_port = TlmOutputPort(specs["mcu_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._enqueued = self._dequeued = 0
    def destroy(self): self._host_port = self._mcu_port = None
    def input_ports(self): return {"host_in": self._host_port} if self._configured else {}
    def output_ports(self): return {"mcu_out": self._mcu_port} if self._mcu_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        return LatencyEstimate(2, 2, 3, 0.9)

    def estimate_energy(self, op):
        return EnergyEstimate(0.05, self.static_power_uw()*1e-6, 0.9)

    def estimate_area(self):
        # SPEC-013: command register file (flops) + optional priority arbiter.
        storage = physical.register_file_area_um2(self._depth, physical.CMDQ_ENTRY_BYTES)
        prio = (physical.logic_block_area_um2(physical.CMDQ_PRIORITY_GATES)
                if self._enable_priority else 0.0)
        return AreaModel(
            um2=storage + prio,
            breakdown={"queue_storage": storage, "priority_logic": prio},
            notes=f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm regfile",
        )

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            tok = self._host_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "enqueue"; yield
            self._enqueued += 1
            self._stage = "dequeue"; yield
            out = TransportToken(
                payload=tok.payload, size_bytes=tok.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "queued_by": self._owner_id},
            )
            yield from self._mcu_port.send(out)
            self._dequeued += 1
