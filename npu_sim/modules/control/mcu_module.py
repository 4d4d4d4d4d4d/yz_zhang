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

from typing import Optional

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
)


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
        return [
            PortSpec(
                name="cmd_in",
                direction=PortDirection.INPUT,
                data_type=DataType.COMMAND,
                width_bits=64,
                fifo_depth=4,
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
        self._configured = True

    def reset(self) -> None:
        pass

    def destroy(self) -> None:
        pass

    # ============== Ports ==============

    def input_ports(self) -> dict[str, ITransportPort]:
        return {}

    def output_ports(self) -> dict[str, ITransportPort]:
        return {}

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
        return ModuleState(busy=False, current_op=None)
