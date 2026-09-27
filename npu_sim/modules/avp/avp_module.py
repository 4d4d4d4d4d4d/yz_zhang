"""AVP: Activation & Vector Post-processor — nonlinear / normalization stage.

Reference: SPEC-005 §5. GELU / softmax / layernorm / pooling at the tail of the
datapath. Runtime follows the Phase 2 Python convention (ADR-001.1).
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


# Transcendental functions cost 2 cycles/lane-group; pooling is cheap (1).
_OP_COST = {"gelu": 2, "softmax": 2, "layernorm": 2, "pooling": 1}


@ModuleRegistry.register
class AVP(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "AVP"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "vector_width": {"type": "integer", "minimum": 1, "maximum": 64, "default": 16},
                "support_softmax": {"type": "boolean", "default": True},
                "support_layernorm": {"type": "boolean", "default": True},
                "support_pooling": {"type": "boolean", "default": False},
                "lut_entries": {"type": "integer", "minimum": 16, "maximum": 1024, "default": 256},
            },
            "required": ["vector_width"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # Area / static-power / energy come from the physical model (SPEC-013:
        # estimate_area / static_power_uw / estimate_energy), scaling with
        # vector_width and lut_entries. The numeric fields below are retained
        # only for the capability-presence contract and are NOT used for AVP PPA.
        return [
            Capability("gelu", "GELU activation (tanh approximation).", 0.0, 0.0, 0.0),
            Capability("softmax", "Softmax along last axis.", 0.0, 0.0, 0.0),
            Capability("layernorm", "Layer normalization.", 0.0, 0.0, 0.0),
            Capability("pooling", "Spatial pooling.", 0.0, 0.0, 0.0),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("in_data", PortDirection.INPUT, DataType.DATA, 512, 8),
            PortSpec("in_cmd", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("out_data", PortDirection.OUTPUT, DataType.DATA, 512, 16),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False

        self._vw: int = 16
        self._support_softmax: bool = True
        self._support_layernorm: bool = True
        self._support_pooling: bool = False
        self._lut_entries: int = 256
        self._active_caps: list[str] = []
        self._stage: str = "idle"

        self._processed: int = 0
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
            raise RuntimeError("AVP.configure() can only be called once.")
        self._vw = config["vector_width"]
        self._support_softmax = config.get("support_softmax", True)
        self._support_layernorm = config.get("support_layernorm", True)
        self._support_pooling = config.get("support_pooling", False)
        self._lut_entries = config.get("lut_entries", 256)

        self._active_caps = ["gelu"]
        if self._support_softmax:
            self._active_caps.append("softmax")
        if self._support_layernorm:
            self._active_caps.append("layernorm")
        if self._support_pooling:
            self._active_caps.append("pooling")

        specs = {p.name: p for p in self.port_specs()}
        self._in_data_port = TlmInputPort(specs["in_data"], self._owner_id, self._clock)
        self._in_cmd_port = TlmInputPort(specs["in_cmd"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["out_data"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._processed = 0
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
        # The op must map to an active capability, else it is unsupported.
        op = operation.op_type
        if op not in self._active_caps or not n:
            return LatencyEstimate(0, 0, 0, confidence=0.6)
        cycles = -(-n // self._vw) * _OP_COST.get(op, 2)  # ceil * cost
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=int(cycles * 1.1),
            max_cycles=int(cycles * 1.5),
            confidence=0.6,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        """Dynamic energy = elements × per-element (LUT read + FP interpolation)
        energy (SPEC-013, Horowitz SRAM read + FP ops), not hand-picked."""
        n = operation.shape_info.get("n_elements", 0)
        per_elem_pj = physical.avp_energy_per_elem_pj(self._active_caps)
        return EnergyEstimate(
            dynamic_pj=per_elem_pj * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.6,
        )

    def estimate_area(self) -> AreaModel:
        """Area from the physical model (SPEC-013): FP-ALU array (∝ vector_width)
        + transcendental LUT SRAM macro (∝ lut_entries)."""
        alu = self._vw * physical.avp_lane_gates(self._active_caps) * physical.A_GATE_UM2
        lut = physical.sram_macro_area_um2(physical.avp_lut_bytes(self._lut_entries))
        um2 = physical.avp_area_um2(self._vw, self._lut_entries, self._active_caps)
        return AreaModel(
            um2=um2,
            breakdown={"alu_array": alu, "lut_sram": lut},
            notes=(
                f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm: "
                f"{self._vw}-wide ALU ({physical.avp_lane_gates(self._active_caps)} "
                f"gates/lane) + {self._lut_entries}-entry LUT"
            ),
        )

    def total_area_um2(self) -> float:
        """Physical AVP area (µm²); overrides the capability-sum default."""
        return self.estimate_area().um2

    def static_power_uw(self) -> float:
        """Leakage from the physical model: ALU gates + LUT SRAM retention."""
        return physical.avp_static_power_uw(
            self._vw, self._lut_entries, self._active_caps
        )

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
    def processed(self) -> int:
        return self._processed

    # ============== Behavior (generator) ==============

    def _act_cycles(self, token: TransportToken) -> int:
        return max(1, -(-token.size_bytes // self._vw) * 2)  # transcendental cost

    def behavior(self) -> Iterator[None]:
        """Poll in_data, apply activation, forward to out_data."""
        while True:
            if self._in_cmd_port is not None:
                self._in_cmd_port.try_receive()

            token = self._in_data_port.try_receive()
            if token is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue

            self._busy = True
            self._stage = "lut_lookup"
            for _ in range(self._act_cycles(token)):
                yield

            self._stage = "emit"
            out_token = TransportToken(
                payload=token.payload,
                size_bytes=token.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "activated": True},
            )
            yield from self._out_port.send(out_token)
            self._processed += 1
