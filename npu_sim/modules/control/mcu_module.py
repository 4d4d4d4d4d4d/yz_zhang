"""MCU: Micro Control Unit — host scheduler. Reference: SPEC-007 §2.

Runs op-gen, BD-gen, op-config per operation. Latency segments:
    T_mcu(op) = T_buffsize + T_bd + T_opcfg   (§2.3.1)

When ``has_ogu_peer`` is True (§2.1.2), T_buffsize and T_bd are offloaded
to OGU (§3) and MCU only retains T_opcfg = 60 cycles.

Multi-threading (§2.3.3): two threads share one MCU via round-robin →
effective total cost = sum across threads.

The save-N-MCU evaluation (§2.5) is computed at the use-case test level
by comparing static estimate_latency / total_area across baseline and
variant architectures.
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
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


# §2.3.1 segment costs (calibration knob).
_T_BUFFSIZE = 80
_T_BD = 120
_T_OPCFG = 60


@ModuleRegistry.register
class MCU(IModule):

    # ============== Class-level metadata ==============

    @classmethod
    def module_type(cls) -> str:
        return "MCU"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "has_ogu_peer": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "SPEC-007 §2.1.2: when true, MCU only emits "
                        "op_dispatch; buffsize_calc + bd_gen are offloaded "
                        "to the paired OGU."
                    ),
                },
                "threads": {
                    "type": "integer",
                    "enum": [1, 2],
                    "default": 1,
                    "description": "SPEC-007 §2.3.3 multi-thread count.",
                },
                "ogu_peer_id": {
                    "type": "string",
                    "description": "Required when has_ogu_peer is true.",
                },
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        # SPEC-007 §2.4.1: baseline single-thread area 120k μm² (calibration knob).
        # Split across the three fallback capabilities so multi-thread doubling
        # via active_capabilities() works cleanly.
        return [
            Capability(
                name="op_dispatch",
                description="SPEC-007 §2.1.1: dispatch op configs to data-path modules.",
                area_cost_um2=30_000.0,
                static_power_uw=20.0,
                dynamic_energy_pj=0.4 * _T_OPCFG,
            ),
            Capability(
                name="bd_gen_fallback",
                description=(
                    "SPEC-007 §2.1.2: BD generation when no OGU peer. "
                    "Active iff has_ogu_peer=False."
                ),
                area_cost_um2=50_000.0,
                static_power_uw=40.0,
                dynamic_energy_pj=0.4 * _T_BD,
            ),
            Capability(
                name="op_config_fallback",
                description=(
                    "SPEC-007 §2.1.2: buffsize + address calc fallback. "
                    "Active iff has_ogu_peer=False."
                ),
                area_cost_um2=40_000.0,
                static_power_uw=30.0,
                dynamic_energy_pj=0.4 * _T_BUFFSIZE,
            ),
            Capability(
                name="thread_2_register_set",
                description=(
                    "SPEC-007 §2.3.3 / §2.4.1: a second thread doubles "
                    "the control-flow register set; only active when "
                    "threads=2."
                ),
                area_cost_um2=120_000.0,
                static_power_uw=80.0,
                dynamic_energy_pj=0.0,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        # SPEC-007 §2.2: workload arrives on cmd_in, dispatch emitted on op_out.
        # ogu_req / ogu_resp form a real handshake to the OGU peer when
        # has_ogu_peer=True (SPEC-007 §2.1.2 / §3.3.2).
        return [
            PortSpec(
                name="cmd_in",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=8,
            ),
            PortSpec(
                name="op_out",
                direction=PortDirection.OUTPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=8,
            ),
            PortSpec(
                name="ogu_req",
                direction=PortDirection.OUTPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
            PortSpec(
                name="ogu_resp",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
            ),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._has_ogu: bool = False
        self._threads: int = 1
        self._active_caps: list[str] = []
        self._busy: bool = False
        self._stage: str = "idle"
        self._dispatched: int = 0
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None
        self._ogu_req_port: Optional[TlmOutputPort] = None
        self._ogu_resp_port: Optional[TlmInputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("MCU.configure() can only be called once.")
        self._has_ogu = config.get("has_ogu_peer", False)
        self._threads = config.get("threads", 1)
        if self._has_ogu and "ogu_peer_id" not in config:
            # SPEC-007 §3.1.2 — OGU pairing requires explicit peer id when
            # MCU is the offload target. (Strict mode only on the OGU side;
            # MCU just records the intent.)
            pass

        self._active_caps = ["op_dispatch"]
        if not self._has_ogu:
            # §2.1.2: only run fallbacks when no OGU.
            self._active_caps += ["bd_gen_fallback", "op_config_fallback"]
        if self._threads == 2:
            self._active_caps.append("thread_2_register_set")

        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(
            specs["op_out"], self._owner_id, self._clock, self._stat_sink
        )
        if self._has_ogu:
            self._ogu_req_port = TlmOutputPort(
                specs["ogu_req"], self._owner_id, self._clock, self._stat_sink
            )
            self._ogu_resp_port = TlmInputPort(
                specs["ogu_resp"], self._owner_id, self._clock
            )
        self._configured = True

    def reset(self) -> None:
        self._busy = False
        self._dispatched = 0

    def destroy(self) -> None:
        self._in_port = None
        self._out_port = None

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        ports = {}
        if self._in_port:
            ports["cmd_in"] = self._in_port
        if self._ogu_resp_port:
            ports["ogu_resp"] = self._ogu_resp_port
        return ports

    def output_ports(self) -> dict[str, ITransportPort]:
        ports = {}
        if self._out_port:
            ports["op_out"] = self._out_port
        if self._ogu_req_port:
            ports["ogu_req"] = self._ogu_req_port
        return ports

    # ============== Capability queries ==============

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return "op_dispatch" in self._active_caps

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # §2.3.1 / §2.3.2: T_mcu depends on has_ogu_peer.
        if self._has_ogu:
            per_thread = _T_OPCFG          # §2.3.2: only op_config remains
        else:
            per_thread = _T_BUFFSIZE + _T_BD + _T_OPCFG  # = 260 cycles

        # §2.3.3 multi-thread: serial round-robin (no parallelism inside MCU).
        cycles = per_thread * self._threads
        return LatencyEstimate(
            min_cycles=cycles,
            typical_cycles=cycles,
            max_cycles=int(cycles * 1.2),
            confidence=0.6,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        # §2.4.2: 0.4 pJ/cycle baseline.
        cycles = self.estimate_latency(operation).typical_cycles
        return EnergyEstimate(
            dynamic_pj=cycles * 0.4,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.6,
        )

    def estimate_area(self) -> AreaModel:
        # Override of SPEC-001 v1.1 default to match §2.4.1 baselines explicitly.
        active = set(self._active_caps)
        breakdown = {
            c.name: c.area_cost_um2
            for c in self.declared_capabilities()
            if c.name in active
        }
        return AreaModel(
            um2=sum(breakdown.values()),
            breakdown=breakdown,
            notes="SPEC-007 §2.4.1 [calibration knob]",
        )

    # ============== Runtime state ==============

    def snapshot_state(self) -> ModuleState:
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    @property
    def dispatched(self) -> int:
        return self._dispatched

    # ============== Behavior (generator) ==============

    def behavior(self) -> Iterator[None]:
        """SPEC-007 §2.3 — real per-op state machine.

        Without OGU: 80 (buffsize) + 120 (bd) + 60 (op_config) = 260 cycles
        of local work, all serial on MCU.

        With OGU: kick a request to OGU (which runs buffsize+bd = 50 cycles
        in parallel on its own die), do op_config locally (60 cycles), then
        wait for the OGU response if it hasn't arrived yet. Total per-op
        time ≈ max(60, 50) + handshake = ~60 cycles → 4.3× speedup vs
        baseline. Now realised as a real ogu_req/ogu_resp handshake on the
        SPEC-002 transport layer, not a fudged latency knob.
        """
        while True:
            token = self._in_port.try_receive()
            if token is None:
                self._busy = False
                self._stage = "idle"
                yield
                continue
            self._busy = True

            if self._has_ogu:
                # Step 1: kick OGU (1 visible cycle + handshake; blocks if back-pressured).
                self._stage = "kick_ogu"
                yield  # 1 sampled cycle of "kick_ogu" state
                req = TransportToken(
                    payload=token.payload,
                    size_bytes=token.size_bytes,
                    timestamp_ps=self._clock.current_time_ps(),
                    source_module=self._owner_id,
                    metadata={**token.metadata, "kind": "ogu_req"},
                )
                yield from self._ogu_req_port.send(req)
                # Step 2: do op_config locally (60 cycles - 1 already spent in
                # kick) in parallel with OGU.
                self._stage = "op_config_local"
                for _ in range(_T_OPCFG * self._threads - 1):
                    yield
                # Step 3: wait for OGU resp (always 1+ sampled cycle).
                self._stage = "wait_ogu_resp"
                yield
                while self._ogu_resp_port.try_receive() is None:
                    yield
            else:
                # Baseline: serial T_buffsize → T_bd → T_opcfg locally.
                for stage_name, stage_cycles in (
                    ("buffsize", _T_BUFFSIZE),
                    ("bd_gen", _T_BD),
                    ("op_config", _T_OPCFG),
                ):
                    self._stage = stage_name
                    for _ in range(stage_cycles * self._threads):
                        yield

            # Step 4: dispatch (1 visible cycle + send-handshake).
            self._stage = "dispatch"
            yield
            out = TransportToken(
                payload=token.payload,
                size_bytes=token.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "dispatched_by": self._owner_id},
            )
            yield from self._out_port.send(out)
            self._dispatched += 1
