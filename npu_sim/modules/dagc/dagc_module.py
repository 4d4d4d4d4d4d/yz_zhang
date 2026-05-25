"""DAGC: BFP unpack / data-alignment controller — first real NPU module.

Faithful implementation of the canonical example in SPEC-001 §5: receives
BFP-packed data on ``in_packed`` (plus optional commands on ``in_cmd``),
unpacks it, and emits the wider unpacked stream on ``out_unpacked``.

Capabilities (SPEC-001 §3.1): ``bfp8_unpack`` and ``bfp16_unpack`` are always
active; ``bfp8_bfp16_mix`` and ``int4_reorder`` are gated by config flags so the
area / power report reflects only what is built (SPEC-001 §3.1 aggregation).

Runtime behavior follows the Phase 2 Python convention (ADR-001.1): a
``behavior()`` generator polling ``TlmInputPort.try_receive`` and pushing with
``yield from TlmOutputPort.send`` so output backpressure is auto-attributed to
the downstream sink (SPEC-002 §3.5).
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


# BFP8:BFP16 traffic split → the BFP16 share of elements. "2:1" means two BFP8
# elements per one BFP16 element, so BFP16 occupies 1/(2+1) of the stream.
_BFP16_SHARE = {"2:1": 1.0 / 3.0, "3:1": 1.0 / 4.0, "4:1": 1.0 / 5.0}


@ModuleRegistry.register
class DAGC(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "DAGC"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "bfp8_unpack_throughput": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 2,
                    "description": "BFP8 unpack lane throughput (elements/cycle).",
                },
                "bfp16_unpack_throughput": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 4,
                    "default": 1,
                    "description": "BFP16 unpack lane throughput (elements/cycle).",
                },
                "bfp_ratio": {
                    "type": "string",
                    "enum": ["2:1", "3:1", "4:1"],
                    "default": "2:1",
                    "description": "BFP8:BFP16 traffic split.",
                },
                "support_4bit_reorder": {"type": "boolean", "default": True},
                "support_mixed_bfp8_bfp16": {
                    "type": "boolean",
                    "default": True,
                    "description": "Build the BFP8 x BFP16 mixed-precision aligner.",
                },
                "join_fifo_depth": {
                    "type": "integer",
                    "minimum": 4,
                    "maximum": 64,
                    "default": 16,
                },
            },
            "required": ["bfp8_unpack_throughput", "bfp16_unpack_throughput"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="bfp8_unpack",
                description="BFP8 format unpack.",
                area_cost_um2=3500.0,
                static_power_uw=12.0,
                dynamic_energy_pj=0.8,
            ),
            Capability(
                name="bfp16_unpack",
                description="BFP16 format unpack.",
                area_cost_um2=6200.0,
                static_power_uw=18.0,
                dynamic_energy_pj=1.5,
            ),
            Capability(
                name="bfp8_bfp16_mix",
                description="BFP8 x BFP16 mixed-precision alignment.",
                area_cost_um2=4100.0,
                static_power_uw=8.0,
                dynamic_energy_pj=1.2,
                depends_on=("bfp8_unpack", "bfp16_unpack"),
            ),
            Capability(
                name="int4_reorder",
                description="INT4 data reorder.",
                area_cost_um2=2300.0,
                static_power_uw=6.0,
                dynamic_energy_pj=0.5,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="in_packed",
                direction=PortDirection.INPUT,
                data_type=DataType.DATA,
                width_bits=128,
                fifo_depth=8,
            ),
            PortSpec(
                name="in_cmd",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="out_unpacked",
                direction=PortDirection.OUTPUT,
                data_type=DataType.DATA,
                width_bits=256,
                fifo_depth=16,
            ),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False

        self._bfp8_tp: int = 2
        self._bfp16_tp: int = 1
        self._bfp16_share: float = _BFP16_SHARE["2:1"]
        self._support_4bit: bool = True
        self._support_mix: bool = True
        self._join_fifo_depth: int = 16
        self._active_caps: list[str] = []

        self._unpacked: int = 0
        self._busy: bool = False
        self._in_packed_port: Optional[TlmInputPort] = None
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
            raise RuntimeError("DAGC.configure() can only be called once.")
        self._bfp8_tp = config["bfp8_unpack_throughput"]
        self._bfp16_tp = config["bfp16_unpack_throughput"]
        self._bfp16_share = _BFP16_SHARE[config.get("bfp_ratio", "2:1")]
        self._support_4bit = config.get("support_4bit_reorder", True)
        self._support_mix = config.get("support_mixed_bfp8_bfp16", True)
        self._join_fifo_depth = config.get("join_fifo_depth", 16)

        self._active_caps = ["bfp8_unpack", "bfp16_unpack"]
        if self._support_mix:
            self._active_caps.append("bfp8_bfp16_mix")
        if self._support_4bit:
            self._active_caps.append("int4_reorder")

        specs = {p.name: p for p in self.port_specs()}
        self._in_packed_port = TlmInputPort(specs["in_packed"], self._owner_id, self._clock)
        self._in_cmd_port = TlmInputPort(specs["in_cmd"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["out_unpacked"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._unpacked = 0
        self._busy = False

    def destroy(self) -> None:
        self._in_packed_port = None
        self._in_cmd_port = None
        self._out_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {"in_packed": self._in_packed_port, "in_cmd": self._in_cmd_port}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out_unpacked": self._out_port} if self._out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        precision = operation.precision
        if precision.is_bfp8():
            cycles = n // self._bfp8_tp
        elif precision.is_bfp16():
            cycles = n // self._bfp16_tp
        elif precision.is_mixed_bfp8_bfp16():
            # Mixed mode: the BFP16 lane is the bottleneck.
            cycles = int(n * self._bfp16_share / self._bfp16_tp)
        else:
            cycles = 0  # unsupported precision
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=int(cycles * 1.1),  # +10% empirical backpressure
            max_cycles=int(cycles * 1.5),
            confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        per_elem_pj = sum(
            c.dynamic_energy_pj
            for c in self.declared_capabilities()
            if c.name in self._active_caps
        )
        return EnergyEstimate(
            dynamic_pj=per_elem_pj * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op="unpack" if self._busy else None,
            internal_fifo_levels={
                "in_packed": self._in_packed_port.fifo_level() if self._in_packed_port else 0,
                "in_cmd": self._in_cmd_port.fifo_level() if self._in_cmd_port else 0,
            },
        )

    @property
    def unpacked(self) -> int:
        return self._unpacked

    # ============== Behavior (generator) ==============

    def _unpack_cycles(self, token: TransportToken) -> int:
        """Cycles to unpack one packed token through the BFP8 lane."""
        return max(1, -(-token.size_bytes // self._bfp8_tp))  # ceil division

    def behavior(self) -> Iterator[None]:
        """Poll in_packed, unpack each token, forward the wider result.

        Commands on in_cmd are drained opportunistically (config of the unpack
        is static in Phase 2). The port may be unconnected, in which case
        try_receive() returns None.
        """
        while True:
            if self._in_cmd_port is not None:
                self._in_cmd_port.try_receive()  # drain; ignored in Phase 2

            token = self._in_packed_port.try_receive()
            if token is None:
                self._busy = False
                yield
                continue

            self._busy = True
            for _ in range(self._unpack_cycles(token)):
                yield

            unpacked_token = TransportToken(
                payload=token.payload,
                size_bytes=token.size_bytes * 2,  # unpacked stream is wider
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "unpacked": True},
            )
            yield from self._out_port.send(unpacked_token)
            self._unpacked += 1
