"""DSB: Data Staging Buffer — SRAM-backed tile staging / broadcast.

Reference: SPEC-005 §2. Sits between DAGC (unpack) and MAC (compute): buffers
tiles, optionally double-buffers to hide downstream latency, and can broadcast
one input tile to several MAC rows.

Runtime follows the Phase 2 Python convention (ADR-001.1, SPEC-005 §1.4): a
``behavior()`` generator polling ``TlmInputPort.try_receive`` and pushing with
``yield from TlmOutputPort.send`` so output backpressure auto-attributes to the
downstream sink (SPEC-002 §3.5).
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim import physical
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.module import (
    AreaModel,
    Capability,
    EnergyEstimate,
    IModule,
    LatencyEstimate,
    ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.services import IEventBus, IStatSink
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
    TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


@ModuleRegistry.register
class DSB(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "DSB"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "buffer_kb": {"type": "integer", "minimum": 1, "maximum": 512, "default": 64},
                "n_banks": {"type": "integer", "minimum": 1, "maximum": 8, "default": 2},
                "read_throughput": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "default": 4,
                    "description": "SRAM read throughput (elements/cycle).",
                },
                "enable_double_buffer": {"type": "boolean", "default": True},
                "broadcast_factor": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 1,
                    "description": "Replicate each staged tile to this many sinks.",
                },
            },
            "required": ["buffer_kb"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # Area / static-power / energy come from the physical model (SPEC-013:
        # estimate_area / static_power_uw / estimate_energy), scaling with the
        # SRAM size (buffer_kb, double-buffering). The numeric fields below are
        # retained only for the capability-presence contract and are NOT used
        # for DSB's PPA.
        return [
            Capability(
                name="tile_buffer",
                description="Basic tile staging + forward.",
                area_cost_um2=0.0, static_power_uw=0.0, dynamic_energy_pj=0.0,
            ),
            Capability(
                name="double_buffer",
                description="Overlapped read/write across banks.",
                area_cost_um2=0.0, static_power_uw=0.0, dynamic_energy_pj=0.0,
                depends_on=("tile_buffer",),
            ),
            Capability(
                name="broadcast",
                description="Replicate one tile to multiple sinks.",
                area_cost_um2=0.0, static_power_uw=0.0, dynamic_energy_pj=0.0,
                depends_on=("tile_buffer",),
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("in_data", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("in_cmd", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("out_data", PortDirection.OUTPUT, DataType.DATA, 256, 16),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False

        self._buffer_kb: int = 64
        self._n_banks: int = 2
        self._read_tp: int = 4
        self._double_buffer: bool = True
        self._broadcast_factor: int = 1
        self._active_caps: list[str] = []

        self._staged: int = 0
        self._stage: str = "idle"
        self._busy: bool = False
        self._in_data_port: Optional[TlmInputPort] = None
        self._in_cmd_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("DSB.configure() can only be called once.")
        self._buffer_kb = config["buffer_kb"]
        self._n_banks = config.get("n_banks", 2)
        self._read_tp = config.get("read_throughput", 4)
        self._double_buffer = config.get("enable_double_buffer", True)
        self._broadcast_factor = config.get("broadcast_factor", 1)

        self._active_caps = ["tile_buffer"]
        if self._double_buffer:
            self._active_caps.append("double_buffer")
        if self._broadcast_factor > 1:
            self._active_caps.append("broadcast")

        specs = {p.name: p for p in self.port_specs()}
        self._in_data_port = TlmInputPort(specs["in_data"], self._owner_id, self._clock)
        self._in_cmd_port = TlmInputPort(specs["in_cmd"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["out_data"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._staged = 0
        self._busy = False

    def destroy(self) -> None:
        self._in_data_port = None
        self._in_cmd_port = None
        self._out_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {"in_data": self._in_data_port, "in_cmd": self._in_cmd_port}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out_data": self._out_port} if self._out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        cycles = -(-n // self._read_tp) if n else 0  # ceil
        # Double-buffering overlaps fill; otherwise add a per-bank fill penalty.
        typical = cycles if self._double_buffer else cycles + self._n_banks
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=typical,
            max_cycles=int(typical * 1.4),
            confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        """Dynamic energy = elements × per-element SRAM-access energy (SPEC-013,
        Horowitz 32b SRAM read 5 pJ), not hand-picked constants."""
        n = operation.shape_info.get("n_elements", 0)
        per_elem_pj = physical.dsb_energy_per_elem_pj(
            self._double_buffer, self._broadcast_factor
        )
        return EnergyEstimate(
            dynamic_pj=per_elem_pj * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        """SRAM-macro area from the physical model (SPEC-013): area scales with
        buffer_kb (and doubles under double-buffering)."""
        um2 = physical.dsb_area_um2(self._buffer_kb, self._double_buffer)
        return AreaModel(
            um2=um2,
            breakdown={"sram_macro": um2},
            notes=(
                f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm: "
                f"{physical.dsb_storage_bytes(self._buffer_kb, self._double_buffer):,} B "
                f"SRAM @ {physical.A_SRAM_BIT_UM2} µm²/bit / "
                f"{physical.SRAM_ARRAY_EFFICIENCY} eff"
            ),
        )

    def total_area_um2(self) -> float:
        """Physical SRAM-macro area (µm²); overrides the capability-sum default."""
        return self.estimate_area().um2

    def static_power_uw(self) -> float:
        """SRAM retention leakage from the physical model."""
        return physical.dsb_static_power_uw(self._buffer_kb, self._double_buffer)

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "in_data": self._in_data_port.fifo_level() if self._in_data_port else 0,
            },
        )

    @property
    def staged(self) -> int:
        return self._staged

    # ============== Behavior (generator) ==============

    def _stage_cycles(self, token: TransportToken) -> int:
        return max(1, -(-token.size_bytes // self._read_tp))  # ceil

    def behavior(self) -> Iterator[None]:
        """Poll in_data, stage each tile, forward broadcast_factor copies."""
        while True:
            if self._in_cmd_port is not None:
                self._in_cmd_port.try_receive()  # drain; static config in Phase 2

            token = self._in_data_port.try_receive()
            if token is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue

            self._busy = True
            self._stage = "stage_tile"
            for _ in range(self._stage_cycles(token)):
                yield

            self._stage = "broadcast"
            for copy_idx in range(self._broadcast_factor):
                staged_token = TransportToken(
                    payload=token.payload,
                    size_bytes=token.size_bytes,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={**token.metadata, "staged": True, "copy": copy_idx},
                )
                yield from self._out_port.send(staged_token)
            self._staged += 1
