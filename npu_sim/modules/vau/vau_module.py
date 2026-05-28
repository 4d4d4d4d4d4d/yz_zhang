"""VAU: Vector Arithmetic Unit — elementwise vector ALU.

Reference: SPEC-005 §4. Bias add, residual add, scale, relu — per-lane
elementwise ops downstream of MAC. Runtime follows the Phase 2 Python
convention (ADR-001.1).
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


@ModuleRegistry.register
class VAU(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "VAU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "lanes": {"type": "integer", "minimum": 1, "maximum": 64, "default": 16},
                "support_max": {"type": "boolean", "default": True},
                "support_relu": {"type": "boolean", "default": True},
            },
            "required": ["lanes"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("vector_add", "Elementwise add.", 4000.0, 9.0, 0.04),
            Capability("vector_mul", "Elementwise multiply.", 5200.0, 11.0, 0.06),
            Capability("vector_max", "Elementwise max.", 2100.0, 5.0, 0.03),
            Capability("relu", "Rectified linear unit.", 900.0, 2.0, 0.01),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("in_a", PortDirection.INPUT, DataType.DATA, 512, 8),
            PortSpec("in_b", PortDirection.INPUT, DataType.DATA, 512, 8),
            PortSpec("in_cmd", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("out", PortDirection.OUTPUT, DataType.DATA, 512, 16),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False

        self._lanes: int = 16
        self._support_max: bool = True
        self._support_relu: bool = True
        self._active_caps: list[str] = []

        self._processed: int = 0
        self._busy: bool = False
        self._in_a_port: Optional[TlmInputPort] = None
        self._in_b_port: Optional[TlmInputPort] = None
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
            raise RuntimeError("VAU.configure() can only be called once.")
        self._lanes = config["lanes"]
        self._support_max = config.get("support_max", True)
        self._support_relu = config.get("support_relu", True)

        self._active_caps = ["vector_add", "vector_mul"]
        if self._support_max:
            self._active_caps.append("vector_max")
        if self._support_relu:
            self._active_caps.append("relu")

        specs = {p.name: p for p in self.port_specs()}
        self._in_a_port = TlmInputPort(specs["in_a"], self._owner_id, self._clock)
        self._in_b_port = TlmInputPort(specs["in_b"], self._owner_id, self._clock)
        self._in_cmd_port = TlmInputPort(specs["in_cmd"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._processed = 0
        self._busy = False

    def destroy(self) -> None:
        self._in_a_port = None
        self._in_b_port = None
        self._in_cmd_port = None
        self._out_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {"in_a": self._in_a_port, "in_b": self._in_b_port, "in_cmd": self._in_cmd_port}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"out": self._out_port} if self._out_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return set(operation.required_capabilities).issubset(set(self._active_caps))

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        cycles = -(-n // self._lanes) if n else 0  # ceil
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=cycles,
            max_cycles=int(cycles * 1.3),
            confidence=0.8,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = operation.shape_info.get("n_elements", 0)
        per_elem_pj = sum(
            c.dynamic_energy_pj for c in self.declared_capabilities()
            if c.name in self._active_caps
        )
        return EnergyEstimate(
            dynamic_pj=per_elem_pj * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.8,
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op="vector" if self._busy else None,
            internal_fifo_levels={
                "in_a": self._in_a_port.fifo_level() if self._in_a_port else 0,
            },
        )

    @property
    def processed(self) -> int:
        return self._processed

    # ============== Behavior (generator) ==============

    def _op_cycles(self, token: TransportToken) -> int:
        return max(1, -(-token.size_bytes // self._lanes))  # ceil

    def behavior(self) -> Iterator[None]:
        """Poll in_a, apply the configured elementwise op, forward to out."""
        while True:
            if self._in_cmd_port is not None:
                self._in_cmd_port.try_receive()
            if self._in_b_port is not None:
                self._in_b_port.try_receive()  # opportunistic second operand drain

            token = self._in_a_port.try_receive()
            if token is None:
                self._busy = False
                yield
                continue

            self._busy = True
            for _ in range(self._op_cycles(token)):
                yield

            out_token = TransportToken(
                payload=token.payload,
                size_bytes=token.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "vau": True},
            )
            yield from self._out_port.send(out_token)
            self._processed += 1
