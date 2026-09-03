"""MAC: Multiply-Accumulate array — the GEMM compute core.

Reference: SPEC-005 §3. Weight-stationary systolic array: weights preload on
``in_weight``, activations stream on ``in_act``, FP32 partial sums flow out on
``out_psum``. Runtime follows the Phase 2 Python convention (ADR-001.1).
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
from npu_sim.interfaces.operation import IOperation, PrecisionKind
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
class MAC(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "MAC"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "array_rows": {"type": "integer", "minimum": 4, "maximum": 256, "default": 32},
                "array_cols": {"type": "integer", "minimum": 4, "maximum": 256, "default": 32},
                "support_bfp16": {"type": "boolean", "default": True},
                "support_fp16": {"type": "boolean", "default": False},
                "psums_per_tile": {
                    "type": "integer", "minimum": 1, "maximum": 256, "default": 1,
                    "description": (
                        "SPEC-008 §2.10: number of partial psums per output "
                        "tile. MAC tags each emitted psum with tile_id and "
                        "partial_idx so an OB can accumulate them. Default 1 "
                        "= each psum is a complete tile (no accumulation, "
                        "backward-compatible with v1.0)."
                    ),
                },
            },
            "required": ["array_rows", "array_cols"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # Area / static-power / energy for MAC are computed from the physical
        # model (SPEC-013, see estimate_area / static_power_uw / estimate_energy),
        # which scales with the PE array size. The per-capability numeric fields
        # below are retained only for the capability-presence contract and are
        # NOT used for MAC's PPA — the physical model supersedes them.
        return [
            Capability("int8_matmul", "INT8 GEMM.", 0.0, 0.0, 0.0),
            Capability("accumulate_fp32", "FP32 partial-sum accumulation.", 0.0, 0.0, 0.0),
            Capability("bfp16_matmul", "BFP16 GEMM.", 0.0, 0.0, 0.0,
                       depends_on=("accumulate_fp32",)),
            Capability("fp16_matmul", "FP16 GEMM.", 0.0, 0.0, 0.0,
                       depends_on=("accumulate_fp32",)),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("in_act", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("in_weight", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("in_cmd", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("out_psum", PortDirection.OUTPUT, DataType.DATA, 512, 16),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False

        self._rows: int = 32
        self._cols: int = 32
        self._support_bfp16: bool = True
        self._support_fp16: bool = False
        self._psums_per_tile: int = 1
        self._active_caps: list[str] = []

        self._psums: int = 0
        self._weight_loaded: bool = False
        self._busy: bool = False
        self._stage: str = "idle"
        self._in_act_port: Optional[TlmInputPort] = None
        self._in_weight_port: Optional[TlmInputPort] = None
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
            raise RuntimeError("MAC.configure() can only be called once.")
        self._rows = config["array_rows"]
        self._cols = config["array_cols"]
        self._support_bfp16 = config.get("support_bfp16", True)
        self._support_fp16 = config.get("support_fp16", False)
        self._psums_per_tile = config.get("psums_per_tile", 1)

        self._active_caps = ["int8_matmul", "accumulate_fp32"]
        if self._support_bfp16:
            self._active_caps.append("bfp16_matmul")
        if self._support_fp16:
            self._active_caps.append("fp16_matmul")

        specs = {p.name: p for p in self.port_specs()}
        self._in_act_port = TlmInputPort(specs["in_act"], self._owner_id, self._clock)
        self._in_weight_port = TlmInputPort(specs["in_weight"], self._owner_id, self._clock)
        self._in_cmd_port = TlmInputPort(specs["in_cmd"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["out_psum"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._psums = 0
        self._weight_loaded = False
        self._busy = False

    def destroy(self) -> None:
        self._in_act_port = None
        self._in_weight_port = None
        self._in_cmd_port = None
        self._out_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {
            "in_act": self._in_act_port,
            "in_weight": self._in_weight_port,
            "in_cmd": self._in_cmd_port,
        }

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out_psum": self._out_port} if self._out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset(set(self._active_caps))

    def _precision_supported(self, kind: PrecisionKind) -> bool:
        if kind == PrecisionKind.INT8:
            return True
        if kind == PrecisionKind.BFP16:
            return self._support_bfp16
        if kind == PrecisionKind.FP16:
            return self._support_fp16
        return False

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        if not self._precision_supported(operation.precision.kind):
            return LatencyEstimate(0, 0, 0, confidence=0.6)
        shape = operation.shape_info
        m = shape.get("m", 1)
        k = shape.get("k", 1)
        n = shape.get("n", 1)
        macs = m * k * n if ("m" in shape or "k" in shape or "n" in shape) \
            else shape.get("n_elements", 0)
        # Same systolic model the runtime uses (finding #2 resolved).
        cycles = self._systolic_cycles(macs) if macs else 0
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=int(cycles * 1.1),
            max_cycles=int(cycles * 1.6),
            confidence=0.6,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        """Dynamic energy = MACs × per-MAC energy (SPEC-013, Horowitz ISSCC'14).

        Per-MAC energy is the multiply + FP32-accumulate cost at the op's
        precision (physical.energy_per_mac_pj), not a hand-picked constant.
        """
        shape = operation.shape_info
        macs = shape.get("m", 1) * shape.get("k", 1) * shape.get("n", 1) \
            if ("m" in shape or "k" in shape or "n" in shape) \
            else shape.get("n_elements", 0)
        per_mac_pj = physical.energy_per_mac_pj(operation.precision.kind)
        return EnergyEstimate(
            dynamic_pj=per_mac_pj * macs,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.6,
        )

    def estimate_area(self) -> AreaModel:
        """PE-array area from the physical model (SPEC-013): area scales with
        the PE count (array_rows × array_cols) and the per-PE gate count of the
        active precision lanes — no longer a size-blind capability constant.
        """
        um2 = physical.mac_array_area_um2(self._rows, self._cols, self._active_caps)
        return AreaModel(
            um2=um2,
            breakdown={"pe_array": um2},
            notes=(
                f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm: "
                f"{self._rows}×{self._cols} PEs × "
                f"{physical.mac_pe_gates(self._active_caps)} gates/PE "
                f"× {physical.A_GATE_UM2} µm²/gate"
            ),
        )

    def total_area_um2(self) -> float:
        """Physical PE-array area (µm²). Overrides the capability-sum default
        so the reported area tracks the array size (SPEC-013)."""
        return self.estimate_area().um2

    def static_power_uw(self) -> float:
        """Leakage from the physical model: total PE gate count × per-gate leak."""
        return physical.mac_array_static_power_uw(
            self._rows, self._cols, self._active_caps
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "in_act": self._in_act_port.fifo_level() if self._in_act_port else 0,
                "in_weight": self._in_weight_port.fifo_level() if self._in_weight_port else 0,
            },
        )

    @property
    def psums(self) -> int:
        return self._psums

    @property
    def stage(self) -> str:
        return self._stage

    # ============== Behavior (generator) ==============

    def _systolic_cycles(self, macs: int) -> int:
        """Weight-stationary systolic cost: ceil(macs / PE) compute + (rows+cols)
        fill/drain. This is the single timing model shared by estimate_latency
        and the runtime (finding #2 resolved: they no longer disagree)."""
        pe = self._rows * self._cols
        if not macs:
            return max(1, self._cols // self._rows) + 1
        compute = -(-macs // pe)  # ceil
        return compute + (self._rows + self._cols)

    def _compute_cycles(self, token=None) -> int:
        """Runtime per-token cost. A token carrying an op_shape (SPEC-012 trace)
        is timed by its matmul size via the systolic model; a shapeless
        synthetic token falls back to the base per-token issue cost."""
        shape = token.metadata.get("op_shape") if token is not None else None
        if shape and any(k in shape for k in ("m", "k", "n")):
            macs = shape.get("m", 1) * shape.get("k", 1) * shape.get("n", 1)
            return self._systolic_cycles(macs)
        return max(1, self._cols // self._rows) + 1

    def behavior(self) -> Iterator[None]:
        """Weight-stationary stream with visible internal stages.

        The pipeline cycle budget is unchanged from v1.0 (preserves the
        SPEC-005 timing contract); only ``current_op`` in snapshot_state
        progresses through named stages so cycle-by-cycle traces show the
        systolic-fill / compute / writeback phases.
        """
        while True:
            if self._in_cmd_port is not None:
                self._in_cmd_port.try_receive()
            if self._in_weight_port is not None:
                if self._in_weight_port.try_receive() is not None:
                    self._weight_loaded = True

            act = self._in_act_port.try_receive()
            if act is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue

            self._busy = True
            total = self._compute_cycles(act)
            # Sub-stage the same total cycles across fill/compute/writeback.
            fill_n = max(0, total // 3)
            compute_n = max(0, total // 3)
            wb_n = total - fill_n - compute_n  # remainder

            self._stage = "systolic_fill"
            for _ in range(fill_n):
                yield
            self._stage = "systolic_compute"
            for _ in range(compute_n):
                yield
            self._stage = "writeback_psum"
            for _ in range(wb_n):
                yield

            # SPEC-008 §2.10: tag psum with (tile_id, partial_idx) so OB can
            # accumulate. psums_per_tile=1 → each psum is a complete tile.
            partial_idx = self._psums % self._psums_per_tile
            tile_id = self._psums // self._psums_per_tile
            is_last_partial = (partial_idx == self._psums_per_tile - 1)
            psum = TransportToken(
                payload=act.payload,
                size_bytes=act.size_bytes * 2,  # FP32 psum is wider
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={
                    **act.metadata,
                    "psum": True,
                    "weight_loaded": self._weight_loaded,
                    "tile_id": tile_id,
                    "partial_idx": partial_idx,
                    "is_last_partial": is_last_partial,
                },
            )
            yield from self._out_port.send(psum)
            self._psums += 1
