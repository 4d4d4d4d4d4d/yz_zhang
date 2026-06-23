"""OGU: Op Generation Unit — scalar coprocessor. Reference: SPEC-007 §3.

Offloads buffsize/address calc + BD generation from MCU. The "2× MCU
load optimization" target (§3.3.2) is asserted at the use-case level:
    T_mcu_baseline(op) / T_mcu_with_ogu(op) ≥ 2.0   (actual: 260/60 ≈ 4.33)
"""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.errors import ConfigurationError
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


# §3.3.1 segment costs (calibration knob).
_T_BUFFSIZE = 20
_T_BD = 30


@ModuleRegistry.register
class OGU(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "OGU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "mcu_peer_id": {
                    "type": "string",
                    "description": (
                        "SPEC-007 §3.1.2: required. Identifies the MCU "
                        "instance this OGU offloads from."
                    ),
                },
            },
            "required": ["mcu_peer_id"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # §3.4.1: 40k μm² total (calibration knob).
        return [
            Capability(
                name="buffsize_calc",
                description="SPEC-007 §3.1.1: scalar buffer-size/address calc.",
                area_cost_um2=15_000.0,
                static_power_uw=10.0,
                dynamic_energy_pj=0.25 * _T_BUFFSIZE,
            ),
            Capability(
                name="address_calc",
                description="SPEC-007 §3.1.1: address calc.",
                area_cost_um2=10_000.0,
                static_power_uw=8.0,
                dynamic_energy_pj=0.25 * _T_BUFFSIZE,
            ),
            Capability(
                name="bd_gen",
                description="SPEC-007 §3.1.1: hardwired BD-gen.",
                area_cost_um2=10_000.0,
                static_power_uw=8.0,
                dynamic_energy_pj=0.25 * _T_BD,
            ),
            Capability(
                name="op_config_assist",
                description="SPEC-007 §3.1.1: assist MCU's op_config emission.",
                area_cost_um2=5_000.0,
                static_power_uw=4.0,
                dynamic_energy_pj=0.0,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec(
                name="req_in",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="resp_out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="cfg_broadcast_out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=8,
            ),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._mcu_peer_id: Optional[str] = None
        self._active_caps: list[str] = []
        self._busy: bool = False
        self._stage: str = "idle"
        self._serviced: int = 0
        self._req_port: Optional[TlmInputPort] = None
        self._resp_port: Optional[TlmOutputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("OGU.configure() can only be called once.")
        # §3.1.2 — mcu_peer_id required.
        if "mcu_peer_id" not in config or not config["mcu_peer_id"]:
            raise ConfigurationError(
                "OGU.configure(): SPEC-007 §3.1.2 requires mcu_peer_id."
            )
        self._mcu_peer_id = config["mcu_peer_id"]
        self._active_caps = [
            "buffsize_calc",
            "address_calc",
            "bd_gen",
            "op_config_assist",
        ]
        specs = {p.name: p for p in self.port_specs()}
        self._req_port = TlmInputPort(specs["req_in"], self._owner_id, self._clock)
        self._resp_port = TlmOutputPort(
            specs["resp_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._configured = True

    def reset(self) -> None:
        self._busy = False
        self._stage = "idle"
        self._serviced = 0

    def destroy(self) -> None:
        self._req_port = None
        self._resp_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        return {"req_in": self._req_port} if self._req_port else {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"resp_out": self._resp_port} if self._resp_port else {}

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        # OGU executes op-gen for any op type its MCU peer dispatches.
        return True

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # §3.3.1: T_ogu = T_buffsize + T_bd = 50 cycles.
        cycles = _T_BUFFSIZE + _T_BD
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=cycles,
            max_cycles=int(cycles * 1.2),
            confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        # §3.4.2: 0.25 pJ/cycle.
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 0.25,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def estimate_area(self) -> AreaModel:
        active = set(self._active_caps)
        breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in active
        }
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-007 §3.4.1 [calibration knob]",
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def serviced(self) -> int:
        return self._serviced

    # ============== Behavior (generator) ==============

    def behavior(self) -> Iterator[None]:
        """SPEC-007 §3.3 — real handshake with MCU peer.

        For each incoming ogu_req: run buffsize (20 cycles) + bd_gen (30
        cycles) = 50 cycles total, then emit ogu_resp. MCU's behavior()
        runs op_config (60 cycles) in parallel; total per-op latency is
        max(50, 60) = 60, not 50+60 — this is true pipeline parallelism
        visible in the per-cycle scheduler trace.
        """
        while True:
            req = self._req_port.try_receive()
            if req is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue
            self._busy = True
            for stage_name, stage_cycles in (
                ("buffsize", _T_BUFFSIZE),
                ("bd_gen", _T_BD),
            ):
                self._stage = stage_name
                for _ in range(stage_cycles):
                    yield
            self._stage = "resp"
            resp = TransportToken(
                payload=req.payload,
                size_bytes=req.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**req.metadata, "kind": "ogu_resp"},
            )
            yield from self._resp_port.send(resp)
            self._serviced += 1
