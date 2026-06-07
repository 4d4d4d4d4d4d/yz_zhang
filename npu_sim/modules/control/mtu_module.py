"""MTU: Memory Transfer Unit — fused TAU+DMA. Reference: SPEC-007 §6.

Independent IModule subclass per ADR-002 (rationale §6.5):
1) port topology differs from TAU+DMA pair,
2) internal addr/data arbitration shared time-base,
3) functional path inlined.

Latency model per §6.3.1:
    T_mtu = max(T_tau, T_dma) (full overlap saves a min(T_tau, T_dma) × 0.8)
"""

from __future__ import annotations

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
)


# Reuse the same per-segment knobs as TAU/DMA so the comparison is apples to apples.
_TAU_CYCLES_PER_BURST = 4
_DRAM_BURST_LATENCY = 40
_BUS_WIDTH_BYTES = 32
_OVERLAP_FACTOR = 0.8       # §6.3.1 calibration knob


@ModuleRegistry.register
class MTU(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "MTU"

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
                "overlap_factor": {
                    "type": "number", "minimum": 0.0, "maximum": 1.0,
                    "default": _OVERLAP_FACTOR,
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # §6.1.1: both TAU and DMA capabilities.
        # §6.4.1: total area 95k μm² < TAU(30k) + DMA(80k) = 110k.
        return [
            Capability(
                name="tensor_address_gen",
                description="SPEC-007 §6.1.1: TAU functionality (shared regs).",
                area_cost_um2=25_000.0,
                static_power_uw=20.0,
                dynamic_energy_pj=_TAU_CYCLES_PER_BURST * 0.3,
            ),
            Capability(
                name="bulk_memory_transfer",
                description="SPEC-007 §6.1.1: DMA functionality (shared bus IO).",
                area_cost_um2=70_000.0,
                static_power_uw=55.0,
                dynamic_energy_pj=1.4,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("descriptor_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 16),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type()
        self._configured = False
        self._burst_lat = _DRAM_BURST_LATENCY
        self._bus_w = _BUS_WIDTH_BYTES
        self._overlap = _OVERLAP_FACTOR

    def assign_id(self, module_id): self._owner_id = module_id
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("MTU.configure() once only.")
        self._burst_lat = config.get("dram_burst_latency", _DRAM_BURST_LATENCY)
        self._bus_w = config.get("bus_width_bytes", _BUS_WIDTH_BYTES)
        self._overlap = config.get("overlap_factor", _OVERLAP_FACTOR)
        self._configured = True

    def reset(self): pass
    def destroy(self): pass
    def input_ports(self): return {}
    def output_ports(self): return {}

    def active_capabilities(self):
        return ["tensor_address_gen", "bulk_memory_transfer"] if self._configured else []

    def can_execute(self, operation): return self._configured

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        import math
        bursts = int(operation.shape_info.get("bursts", 64))
        payload = int(operation.shape_info.get("payload_bytes", 4096))
        t_tau = bursts * _TAU_CYCLES_PER_BURST
        per_burst = self._burst_lat + (payload // bursts) // self._bus_w
        t_dma = bursts * per_burst
        # §6.3.1: T_mtu = T_tau + T_dma - overlap_savings, where
        # overlap_savings ≥ min(T_tau, T_dma) × overlap_factor (lower bound).
        # Use ceil so the lower bound is always honored under int rounding.
        overlap = math.ceil(min(t_tau, t_dma) * self._overlap)
        cycles = t_tau + t_dma - overlap
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.2), confidence=0.7,
        )

    def estimate_energy(self, operation):
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 1.2,  # slightly lower than TAU+DMA combined static avg
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
            notes="SPEC-007 §6.4.1 [calibration knob]",
        )

    def snapshot_state(self): return ModuleState(busy=False)
