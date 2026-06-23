"""OB: Output / Accumulator Buffer. Reference: SPEC-008 §2.

Sits between MAC and VAU. Accumulates psums tagged with
(tile_id, partial_idx) by MAC (§2.10), then flushes complete output
tiles to the downstream VAU. Separates "accumulation depth" from
"MAC compute" so weight/output-stationary tradeoffs can be evaluated
via YAML config alone.
"""

from __future__ import annotations

from typing import Iterator, Optional

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
from npu_sim.interfaces.services import IEventBus, IStatSink, StallReason
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
    TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


# §2.5.1 calibration knob: μm² per KB of accumulator (FP32 regs are expensive).
_AREA_PER_KB_PER_TILE = 1500.0


@ModuleRegistry.register
class OB(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "OB"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "tile_kb": {
                    "type": "integer", "minimum": 1, "maximum": 1024,
                    "default": 16,
                },
                "max_in_flight_tiles": {
                    "type": "integer", "minimum": 1, "maximum": 16,
                    "default": 2,  # double buffer
                },
                "accumulate_depth": {
                    "type": "integer", "minimum": 1, "maximum": 256,
                    "default": 1,
                    "description": (
                        "Number of partial psums expected per output tile. "
                        "Must match MAC's psums_per_tile config."
                    ),
                },
                "support_fp32_acc": {"type": "boolean", "default": True},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="psum_accumulate",
                description="SPEC-008 §2.2.2: in-place psum addition into output tile.",
                area_cost_um2=0.0,           # scaled in estimate_area()
                static_power_uw=0.0,
                dynamic_energy_pj=0.6,
            ),
            Capability(
                name="int32_acc",
                description="INT32 accumulator path.",
                area_cost_um2=2_000.0,
                static_power_uw=2.0,
                dynamic_energy_pj=0.0,
            ),
            Capability(
                name="fp32_acc",
                description="FP32 accumulator path (wider, more power).",
                area_cost_um2=6_000.0,
                static_power_uw=5.0,
                dynamic_energy_pj=0.0,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("psum_in", PortDirection.INPUT, DataType.DATA, 512, 8),
            PortSpec("acc_out", PortDirection.OUTPUT, DataType.DATA, 512, 4),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._tile_kb: int = 16
        self._max_in_flight: int = 2
        self._accumulate_depth: int = 1
        self._support_fp32_acc: bool = True
        self._active_caps: list[str] = []
        # Runtime: tile_id → (acc_bytes_so_far, partials_received).
        self._tiles: dict[int, list[int]] = {}
        self._busy: bool = False
        self._stage: str = "idle"
        self._flushed: int = 0
        self._psums_accepted: int = 0
        # Ports
        self._psum_in_port: Optional[TlmInputPort] = None
        self._acc_out_port: Optional[TlmOutputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("OB.configure() once only.")
        self._tile_kb = config.get("tile_kb", 16)
        self._max_in_flight = config.get("max_in_flight_tiles", 2)
        self._accumulate_depth = config.get("accumulate_depth", 1)
        self._support_fp32_acc = config.get("support_fp32_acc", True)

        self._active_caps = ["psum_accumulate", "int32_acc"]
        if self._support_fp32_acc:
            self._active_caps.append("fp32_acc")

        specs = {p.name: p for p in self.port_specs()}
        self._psum_in_port = TlmInputPort(specs["psum_in"], self._owner_id, self._clock)
        self._acc_out_port = TlmOutputPort(
            specs["acc_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self) -> None:
        self._tiles = {}
        self._busy = False
        self._stage = "idle"
        self._flushed = 0
        self._psums_accepted = 0

    def destroy(self) -> None:
        self._psum_in_port = None
        self._acc_out_port = None
        self._cmd_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {"psum_in": self._psum_in_port, "cmd_in": self._cmd_port}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"acc_out": self._acc_out_port} if self._acc_out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return "psum_accumulate" in self._active_caps

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # Per partial: 1 cycle accumulate.
        depth = max(1, self._accumulate_depth)
        cycles = depth + 1  # depth accumulates + 1 flush
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.2), confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        return EnergyEstimate(
            dynamic_pj=0.6 * max(1, self._accumulate_depth),
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        # §2.5.1: tile_kb × max_in_flight_tiles × 1500 μm²/KB.
        storage_um2 = self._tile_kb * self._max_in_flight * _AREA_PER_KB_PER_TILE
        cap_breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in self._active_caps and c.name != "psum_accumulate"
        }
        breakdown = {"psum_accumulate": storage_um2, **cap_breakdown}
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-008 §2.5.1 [calibration knob]",
        )

    def total_area_um2(self) -> float:
        return self.estimate_area().um2

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "psum_in": self._psum_in_port.fifo_level() if self._psum_in_port else 0,
                "in_flight_tiles": len(self._tiles),
            },
        )

    @property
    def flushed_tiles(self) -> int:
        return self._flushed

    @property
    def psums_accepted(self) -> int:
        return self._psums_accepted

    # ============== Behavior (generator) ==============

    def _emit_overflow_stall(self) -> None:
        if self._stat_sink is None:
            return
        try:
            self._stat_sink.record_stall(
                module=self._owner_id,
                reason=StallReason.OTHER,
                duration_ps=self._clock.period_ps,
                caused_by="ob_overflow",
            )
        except Exception:  # noqa: BLE001
            pass

    def behavior(self) -> Iterator[None]:
        """SPEC-008 §2.4 — accept psum, accumulate, flush completed tiles."""
        while True:
            self._busy = False
            self._stage = "idle"
            if self._cmd_port is not None:
                self._cmd_port.try_receive()

            psum = self._psum_in_port.try_receive() if self._psum_in_port else None
            if psum is None:
                yield
                continue

            self._busy = True
            self._stage = "accumulate"
            tile_id = int(psum.metadata.get("tile_id", 0))
            is_last_partial = bool(psum.metadata.get("is_last_partial", True))

            tile_max_bytes = self._tile_kb * 1024

            # §2.4.4 overflow: new tile would exceed max_in_flight_tiles.
            if tile_id not in self._tiles and len(self._tiles) >= self._max_in_flight:
                self._stage = "wait_acc"
                self._emit_overflow_stall()
                yield
                continue

            # Accumulate (1 cycle in-place add).
            entry = self._tiles.setdefault(tile_id, [0, 0])
            entry[0] = min(tile_max_bytes, entry[0] + psum.size_bytes)
            entry[1] += 1
            self._psums_accepted += 1
            yield  # 1 cycle for the add

            # Flush when last partial arrives.
            if is_last_partial or entry[1] >= self._accumulate_depth:
                self._stage = "flush_tile"
                out = TransportToken(
                    payload=psum.payload,
                    size_bytes=entry[0],
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={**psum.metadata, "accumulated_tile": True, "tile_id": tile_id},
                )
                yield from self._acc_out_port.send(out)
                self._flushed += 1
                del self._tiles[tile_id]
