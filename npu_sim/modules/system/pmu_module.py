"""PMU: Performance Monitor Unit. SPEC-010 §1.

Periodically samples its peer modules' busy/idle state and counts up
cycle-level counters. Does not participate in token flow.
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel, Capability, EnergyEstimate, IModule, LatencyEstimate, ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.transport import DataType, ITransportPort, PortDirection, PortSpec


@ModuleRegistry.register
class PMU(IModule):

    @classmethod
    def module_type(cls) -> str: return "PMU"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "n_counters": {"type": "integer", "minimum": 1, "maximum": 32, "default": 3},
                "report_period_cycles": {"type": "integer", "minimum": 1, "default": 100},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("cycle_counter", "Global cycle count.", 0.0, 0.1, 0.05),
            Capability("event_counter", "Per-module event counter.", 0.0, 0.1, 0.05),
            Capability("module_busy_tracker", "Sample peer busy/idle.", 0.0, 0.2, 0.05),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("event_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("report_out", PortDirection.OUTPUT, DataType.COMMAND, 64, 4),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._n_counters = 3; self._report_period = 100
        self._busy = False; self._stage = "idle"
        self._cycle_count = 0; self._samples = 0
        self._event_port = None
        self._report_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("PMU.configure() once.")
        self._n_counters = config.get("n_counters", 3)
        self._report_period = config.get("report_period_cycles", 100)
        # Ports left disconnected by default; PMU works as a passive observer.
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._cycle_count = 0; self._samples = 0
    def destroy(self): pass
    def input_ports(self): return {}
    def output_ports(self): return {}
    def active_capabilities(self): return ["cycle_counter", "event_counter", "module_busy_tracker"]
    def can_execute(self, op): return True

    def estimate_latency(self, op):
        return LatencyEstimate(self._report_period, self._report_period, self._report_period + 1, 0.9)

    def estimate_energy(self, op):
        return EnergyEstimate(0.05 * self._report_period, self.static_power_uw()*1e-6, 0.9)

    def estimate_area(self):
        # §1.4: 5_000 μm² per counter [calibration knob].
        area = self._n_counters * 5_000.0
        return AreaModel(um2=area, breakdown={"counters": area}, notes="SPEC-010 §1.4 [calibration knob]")

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def samples_taken(self) -> int: return self._samples

    def behavior(self) -> Iterator[None]:
        """§1.3: increment cycle counter every tick; flush 'report' every
        report_period_cycles. No token flow; counters live in module state.
        """
        while True:
            self._cycle_count += 1
            if self._cycle_count % self._report_period == 0:
                self._busy = True
                self._stage = "flush_report"
                self._samples += 1
            else:
                self._busy = True if (self._cycle_count % 2 == 0) else False
                self._stage = "sample" if self._busy else "idle"
            yield
