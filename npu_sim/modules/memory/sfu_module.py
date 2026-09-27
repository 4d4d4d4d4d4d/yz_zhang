"""SFU: Special Function Unit. Reference: SPEC-008 §4.

Transcendentals (exp / log / rsqrt / div, optional sin / cos) with
calibrated per-op latency. AVP can offload to an SFU peer for
softmax / layernorm accuracy.
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


# §4.4.1 calibration knobs (cycles).
_OP_LATENCY = {
    "exp": 8, "log": 8, "rsqrt": 12, "div": 14, "sin": 16, "cos": 16,
}
_TRIG_OPS = {"sin", "cos"}


@ModuleRegistry.register
class SFU(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "SFU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "enable_trig": {"type": "boolean", "default": False},
                "default_op": {
                    "type": "string",
                    "enum": list(_OP_LATENCY.keys()),
                    "default": "exp",
                    "description": (
                        "Op applied to inbound operand tokens whose metadata "
                        "does not specify op_type. Lets a basic pipeline drive "
                        "the SFU without an MCU emitting op_type per token."
                    ),
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("exp", "exp(x)", 5_000.0, 4.0, 2.5),
            Capability("log", "log(x)", 5_000.0, 4.0, 2.5),
            Capability("rsqrt", "1/sqrt(x)", 7_000.0, 5.0, 3.0),
            Capability("div", "a/b", 8_000.0, 6.0, 3.5),
            Capability("sin", "sin(x)", 4_000.0, 3.5, 2.0),
            Capability("cos", "cos(x)", 4_000.0, 3.5, 2.0),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("req_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("operand_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("result_out", PortDirection.OUTPUT, DataType.DATA, 256, 8),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._enable_trig: bool = False
        self._default_op: str = "exp"
        self._active_caps: list[str] = []
        self._busy: bool = False
        self._stage: str = "idle"
        self._completed: int = 0
        self._req_port: Optional[TlmInputPort] = None
        self._operand_port: Optional[TlmInputPort] = None
        self._result_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("SFU.configure() once only.")
        self._enable_trig = config.get("enable_trig", False)
        self._default_op = config.get("default_op", "exp")
        # §4.2.2: exp/log/rsqrt/div always; trig only if enable_trig.
        self._active_caps = ["exp", "log", "rsqrt", "div"]
        if self._enable_trig:
            self._active_caps += ["sin", "cos"]

        specs = {p.name: p for p in self.port_specs()}
        self._req_port = TlmInputPort(specs["req_in"], self._owner_id, self._clock)
        self._operand_port = TlmInputPort(
            specs["operand_in"], self._owner_id, self._clock
        )
        self._result_port = TlmOutputPort(
            specs["result_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._busy = False
        self._stage = "idle"
        self._completed = 0

    def destroy(self) -> None:
        self._req_port = None
        self._operand_port = None
        self._result_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {"req_in": self._req_port, "operand_in": self._operand_port}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"result_out": self._result_port} if self._result_port else {}

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # Default op cycles unless op metadata says otherwise.
        op_type = getattr(operation, "_op_type", None) or self._default_op
        cycles = _OP_LATENCY.get(op_type, _OP_LATENCY["exp"])
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.2), confidence=0.8,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        return EnergyEstimate(
            dynamic_pj=2.5,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        # §4.5.1: base 25000 + 8000 if trig enabled.
        breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in self._active_caps
        }
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-008 §4.5.1 [calibration knob]",
        )

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "operand_in": self._operand_port.fifo_level() if self._operand_port else 0,
            },
        )

    @property
    def completed(self) -> int:
        return self._completed

    # ============== Behavior ==============

    def _emit_unsupported_stall(self) -> None:
        if self._stat_sink is None:
            return
        try:
            self._stat_sink.record_stall(
                module=self._owner_id,
                reason=StallReason.OTHER,
                duration_ps=self._clock.period_ps,
                caused_by="sfu_unsupported_op",
            )
        except Exception:  # noqa: BLE001
            pass

    def behavior(self) -> Iterator[None]:
        """§4.4 — receive operand, compute requested op, emit result.

        Op selection: prefer token.metadata['op_type']; else fall back to
        configured default_op.
        """
        while True:
            self._busy = False
            self._stage = "idle"
            # Drain req port (config, optional).
            req = self._req_port.try_receive() if self._req_port else None

            tok = self._operand_port.try_receive() if self._operand_port else None
            if tok is None:
                yield
                continue

            self._busy = True
            self._stage = "recv_req"
            yield  # 1 sampled cycle of request reception

            op_type = (req.metadata.get("op_type") if req is not None else None) or \
                      tok.metadata.get("op_type") or self._default_op
            if op_type in _TRIG_OPS and not self._enable_trig:
                self._stage = "unsupported"
                self._emit_unsupported_stall()
                yield
                continue
            if op_type not in _OP_LATENCY:
                self._stage = "unsupported"
                self._emit_unsupported_stall()
                yield
                continue

            self._stage = f"compute_{op_type}"
            for _ in range(_OP_LATENCY[op_type]):
                yield

            self._stage = "emit_result"
            out = TransportToken(
                payload=tok.payload,
                size_bytes=tok.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "sfu_op": op_type},
            )
            yield from self._result_port.send(out)
            self._completed += 1
