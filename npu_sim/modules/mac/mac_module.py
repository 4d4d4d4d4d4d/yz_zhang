"""MAC: Multiply-Accumulate array — the GEMM compute core.

Reference: SPEC-005 §3. Weight-stationary systolic array: weights preload on
``in_weight``, activations stream on ``in_act``, FP32 partial sums flow out on
``out_psum``. Runtime follows the Phase 2 Python convention (ADR-001.1).
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.module import (
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
            },
            "required": ["array_rows", "array_cols"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("int8_matmul", "INT8 GEMM.", 42000.0, 90.0, 0.05),
            Capability("accumulate_fp32", "FP32 partial-sum accumulation.", 8000.0, 20.0, 0.02),
            Capability("bfp16_matmul", "BFP16 GEMM.", 15000.0, 35.0, 0.08,
                       depends_on=("accumulate_fp32",)),
            Capability("fp16_matmul", "FP16 GEMM.", 18000.0, 40.0, 0.1,
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
        pe = self._rows * self._cols
        fill = self._rows + self._cols
        compute = -(-macs // pe) if macs else 0  # ceil
        cycles = compute + fill if macs else 0
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=int(cycles * 1.1),
            max_cycles=int(cycles * 1.6),
            confidence=0.6,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        shape = operation.shape_info
        macs = shape.get("m", 1) * shape.get("k", 1) * shape.get("n", 1) \
            if ("m" in shape or "k" in shape or "n" in shape) \
            else shape.get("n_elements", 0)
        per_mac_pj = sum(
            c.dynamic_energy_pj for c in self.declared_capabilities()
            if c.name in self._active_caps
        )
        return EnergyEstimate(
            dynamic_pj=per_mac_pj * macs,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.6,
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

    def _compute_cycles(self) -> int:
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
            total = self._compute_cycles()
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

            psum = TransportToken(
                payload=act.payload,
                size_bytes=act.size_bytes * 2,  # FP32 psum is wider
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**act.metadata, "psum": True, "weight_loaded": self._weight_loaded},
            )
            yield from self._out_port.send(psum)
            self._psums += 1
