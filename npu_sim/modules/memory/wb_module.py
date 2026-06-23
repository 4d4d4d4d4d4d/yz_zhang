"""WB: Weight Buffer — independent on-chip weight store. Reference: SPEC-008 §1.

Splits the "weight storage" role out of DSB so weight-stationary
evaluation, prefetch benefit, and capacity-overflow cost can be
measured directly via YAML config changes.

Capabilities:
  - weight_storage (always)
  - weight_prefetch (gated by enable_prefetch)
  - weight_compression (gated by enable_compression — capability flag
    only in v1.0; actual algo deferred to v1.1)
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


# SPEC-008 §1.4 calibration knobs.
_DEFAULT_WRITE_BW = 32      # bytes per cycle
_DEFAULT_READ_BW = 64       # bytes per cycle
_DEFAULT_CAPACITY_KB = 256


@ModuleRegistry.register
class WB(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "WB"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "capacity_kb": {
                    "type": "integer", "minimum": 1, "maximum": 16_384,
                    "default": _DEFAULT_CAPACITY_KB,
                },
                "write_bw_bytes_per_cycle": {
                    "type": "integer", "minimum": 1, "default": _DEFAULT_WRITE_BW,
                },
                "read_bw_bytes_per_cycle": {
                    "type": "integer", "minimum": 1, "default": _DEFAULT_READ_BW,
                },
                "enable_prefetch": {"type": "boolean", "default": False},
                "enable_compression": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # SPEC-008 §1.5 area attached to capabilities so estimate_area's
        # default aggregation works; per-KB scaling done in estimate_area().
        return [
            Capability(
                name="weight_storage",
                description="SPEC-008 §1.2.2: persistent weight tile store.",
                area_cost_um2=0.0,           # actual cost computed in estimate_area
                static_power_uw=0.0,
                dynamic_energy_pj=0.4,        # per byte read+write avg
            ),
            Capability(
                name="weight_prefetch",
                description="SPEC-008 §1.4.3: background fill independent of serve port.",
                area_cost_um2=4_000.0,
                static_power_uw=3.0,
                dynamic_energy_pj=0.0,
            ),
            Capability(
                name="weight_compression",
                description="SPEC-008 §1.2.2: decompress on read (algo deferred to v1.1).",
                area_cost_um2=6_000.0,
                static_power_uw=4.0,
                dynamic_energy_pj=0.1,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("weight_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("weight_out", PortDirection.OUTPUT, DataType.DATA, 256, 8),
            PortSpec("prefetch_cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._capacity_bytes: int = _DEFAULT_CAPACITY_KB * 1024
        self._write_bw: int = _DEFAULT_WRITE_BW
        self._read_bw: int = _DEFAULT_READ_BW
        self._enable_prefetch: bool = False
        self._enable_compression: bool = False
        self._active_caps: list[str] = []
        # Runtime state
        self._stored_bytes: int = 0
        self._busy: bool = False
        self._stage: str = "idle"
        self._weights_loaded: int = 0
        self._weights_served: int = 0
        # Ports
        self._weight_in_port: Optional[TlmInputPort] = None
        self._weight_out_port: Optional[TlmOutputPort] = None
        self._prefetch_port: Optional[TlmInputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("WB.configure() once only.")
        capacity_kb = config.get("capacity_kb", _DEFAULT_CAPACITY_KB)
        self._capacity_bytes = capacity_kb * 1024
        self._write_bw = config.get("write_bw_bytes_per_cycle", _DEFAULT_WRITE_BW)
        self._read_bw = config.get("read_bw_bytes_per_cycle", _DEFAULT_READ_BW)
        self._enable_prefetch = config.get("enable_prefetch", False)
        self._enable_compression = config.get("enable_compression", False)

        self._active_caps = ["weight_storage"]
        if self._enable_prefetch:
            self._active_caps.append("weight_prefetch")
        if self._enable_compression:
            self._active_caps.append("weight_compression")

        specs = {p.name: p for p in self.port_specs()}
        self._weight_in_port = TlmInputPort(specs["weight_in"], self._owner_id, self._clock)
        self._weight_out_port = TlmOutputPort(
            specs["weight_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._prefetch_port = TlmInputPort(
            specs["prefetch_cmd_in"], self._owner_id, self._clock
        )
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self) -> None:
        self._stored_bytes = 0
        self._busy = False
        self._stage = "idle"
        self._weights_loaded = 0
        self._weights_served = 0

    def destroy(self) -> None:
        self._weight_in_port = None
        self._weight_out_port = None
        self._prefetch_port = None
        self._cmd_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {
            "weight_in": self._weight_in_port,
            "prefetch_cmd_in": self._prefetch_port,
            "cmd_in": self._cmd_port,
        }

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"weight_out": self._weight_out_port} if self._weight_out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return "weight_storage" in self._active_caps

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # Default: one read per op (weight serve), scales with payload.
        payload = int(operation.shape_info.get("payload_bytes", 1024))
        cycles = 1 + max(1, payload // self._read_bw)
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.2), confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        payload = int(operation.shape_info.get("payload_bytes", 1024))
        # §1.5.3: 0.3 pJ/byte read + 0.5 pJ/byte write (avg per access).
        dynamic = payload * 0.3
        return EnergyEstimate(
            dynamic_pj=dynamic,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        # §1.5.1: capacity_kb × 1200 μm²/KB, plus capability area.
        capacity_kb = self._capacity_bytes // 1024
        storage_um2 = capacity_kb * 1200.0
        cap_breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in self._active_caps and c.name != "weight_storage"
        }
        breakdown = {"weight_storage": storage_um2, **cap_breakdown}
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-008 §1.5.1 [calibration knob]",
        )

    def static_power_uw(self) -> float:
        # §1.5.2: capacity_kb × 0.5 μW/KB.
        capacity_kb = self._capacity_bytes // 1024
        base = capacity_kb * 0.5
        cap_extra = sum(
            c.static_power_uw for c in self.declared_capabilities()
            if c.name in self._active_caps and c.name != "weight_storage"
        )
        return base + cap_extra

    def total_area_um2(self) -> float:
        # Override SPEC-001 default so the capacity-scaled storage area
        # (computed in estimate_area) flows into evaluation.total_area_um2.
        return self.estimate_area().um2

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "weight_in": self._weight_in_port.fifo_level() if self._weight_in_port else 0,
                "prefetch_cmd_in": self._prefetch_port.fifo_level() if self._prefetch_port else 0,
            },
        )

    @property
    def stored_bytes(self) -> int:
        return self._stored_bytes

    @property
    def weights_served(self) -> int:
        return self._weights_served

    # ============== Behavior (generator) ==============

    def _emit_overflow_stall(self) -> None:
        if self._stat_sink is None:
            return
        try:
            self._stat_sink.record_stall(
                module=self._owner_id,
                reason=StallReason.OTHER,
                duration_ps=self._clock.period_ps,
                caused_by="weight_overflow",
            )
        except Exception:  # noqa: BLE001 — sink interface may evolve
            pass

    def behavior(self) -> Iterator[None]:
        """SPEC-008 §1.4 — weight load, prefetch, serve.

        Priority each cycle:
          1. Drain pending prefetch commands (if enabled)
          2. Try to accept a new weight_in token (loads tile into store)
          3. If a downstream MAC is consuming, serve from weight_out
        """
        while True:
            self._busy = False
            self._stage = "idle"

            # 1. prefetch_cmd drain — counts as background work this cycle.
            pref = self._prefetch_port.try_receive() if self._prefetch_port else None
            if pref is not None and self._enable_prefetch:
                self._busy = True
                self._stage = "prefetch"
                # Prefetch advances 1 cycle of background fill; doesn't block
                # the serve path (independent read port per §1.4.3).

            # 2. weight load — accept incoming weight tile.
            tok = self._weight_in_port.try_receive() if self._weight_in_port else None
            if tok is not None:
                if self._stored_bytes + tok.size_bytes > self._capacity_bytes:
                    # §1.4.4 — overflow.
                    self._busy = True
                    self._stage = "overflow_drain"
                    self._emit_overflow_stall()
                    yield
                    continue
                self._busy = True
                self._stage = "load_weight"
                load_cycles = max(1, tok.size_bytes // self._write_bw)
                for _ in range(load_cycles):
                    yield
                self._stored_bytes += tok.size_bytes
                self._weights_loaded += 1
                continue

            # 3. serve — once per loaded tile (weight-stationary semantic:
            #    a tile is loaded then served exactly once to its consumer).
            #    Weights themselves stay resident; only the "serve token"
            #    flow is bounded so the test workload terminates.
            if self._weights_served < self._weights_loaded:
                self._busy = True
                self._stage = "serve_weight"
                serve_bytes = min(self._stored_bytes, self._read_bw)
                serve_cycles = 1 + max(1, serve_bytes // self._read_bw)
                for _ in range(serve_cycles):
                    yield
                served = TransportToken(
                    payload=None,
                    size_bytes=serve_bytes,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={"weight_tile": True, "served_by": self._owner_id},
                )
                yield from self._weight_out_port.send(served)
                self._weights_served += 1
            else:
                yield
