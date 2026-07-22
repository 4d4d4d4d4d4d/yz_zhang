"""TraceProducer: trace-driven stimulus source. SPEC-012.

Unlike Producer (homogeneous synthetic tokens), TraceProducer replays a
real operator sequence — a list of ops with per-op shape — emitting one
token per op whose size and metadata are derived from the operator. This
lets a chip run a real model layer (attention / MLP / conv) instead of
abstract token flux.

Trace is inlined in config (`ops` list) so the whole workload stays in
YAML and the YAML-driven evaluation contract keeps holding.
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
from npu_sim.interfaces.services import IEventBus, IStatSink
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
    TransportToken,
)
from npu_sim.runtime.ports import TlmOutputPort


# SPEC-012 §1.4 precision → bytes per element.
_PRECISION_BYTES = {
    "int4": 1,   # sub-byte rounds up to 1
    "int8": 1,
    "int16": 2,
    "int32": 4,
    "fp16": 2,
    "bf16": 2,
    "bfp8": 1,
    "bfp16": 2,
    "fp32": 4,
}
_DEFAULT_BYTES = 64


def _op_output_bytes(op: dict) -> int:
    """SPEC-012 §1.4: derive token size from operator shape."""
    op_type = op.get("op_type", "")
    prec = op.get("precision", "fp32")
    pbytes = _PRECISION_BYTES.get(prec, 4)
    if op_type == "matmul" and ("m" in op or "n" in op):
        m = int(op.get("m", 1))
        n = int(op.get("n", 1))
        return max(1, m * n * pbytes)
    if "n_elements" in op:
        return max(1, int(op["n_elements"]) * 4)  # elementwise: FP32 out
    return _DEFAULT_BYTES


@ModuleRegistry.register
class TraceProducer(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "TraceProducer"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "SPEC-012 §1.3: operator sequence to replay.",
                },
                "send_rate_cycles_per_token": {
                    "type": "integer", "minimum": 1, "default": 1,
                },
                "repeat": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["ops"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="trace_replay",
                description="SPEC-012: replay an operator trace as a token stream.",
                area_cost_um2=0.0,
                static_power_uw=0.0,
                dynamic_energy_pj=0.01,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.DATA,
                width_bits=256,
                fifo_depth=1,
            ),
        ]

    # ============== state ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._ops: list[dict] = []
        self._rate: int = 1
        self._repeat: int = 1
        self._emitted: int = 0
        self._busy: bool = False
        self._stage: str = "idle"
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        self._ops = list(config["ops"])
        self._rate = config.get("send_rate_cycles_per_token", 1)
        self._repeat = config.get("repeat", 1)
        out_spec = next(p for p in self.port_specs() if p.name == "out")
        self._out_port = TlmOutputPort(
            port_spec=out_spec,
            owner_module_id=self._owner_id,
            clock=self._clock,
            stat_sink=self._stat_sink,
        )

    def reset(self) -> None:
        self._emitted = 0
        self._busy = False
        self._stage = "idle"

    def destroy(self) -> None:
        self._out_port = None

    # ============== ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        return {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out": self._out_port} if self._out_port else {}

    # ============== queries ==============

    def active_capabilities(self) -> list[str]:
        return ["trace_replay"]

    def can_execute(self, operation: IOperation) -> bool:
        return True

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = len(self._ops) * self._repeat
        return LatencyEstimate(n, n, n, 0.9)

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        return EnergyEstimate(0.01 * len(self._ops), 0.0, 0.9)

    def estimate_area(self) -> AreaModel:
        return AreaModel(um2=0.0, breakdown={}, notes="virtual")

    def total_area_um2(self) -> float:
        return 0.0

    def snapshot_state(self) -> ModuleState:
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def emitted(self) -> int:
        return self._emitted

    @property
    def total_ops(self) -> int:
        return len(self._ops) * self._repeat

    # ============== behavior ==============

    def behavior(self) -> Iterator[None]:
        """SPEC-012 §1.4: replay ops in order; each op → one token whose
        size/metadata are derived from the operator shape."""
        op_index = 0
        for _rep in range(self._repeat):
            for op in self._ops:
                self._busy = True
                self._stage = "replay_op"
                size = _op_output_bytes(op)
                self._stage = "emit"
                token = TransportToken(
                    payload=None,
                    size_bytes=size,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={
                        "op_type": op.get("op_type", "unknown"),
                        "op_index": op_index,
                        "op_shape": {k: v for k, v in op.items() if k != "op_type"},
                        "trace_token": True,
                    },
                )
                yield from self._out_port.send(token)
                self._emitted += 1
                op_index += 1
                # inter-op spacing
                for _ in range(max(0, self._rate - 1)):
                    self._busy = False
                    self._stage = "idle"
                    yield
        # trace exhausted — idle forever (keeps scheduler alive for peers)
        while True:
            self._busy = False
            self._stage = "idle"
            yield
