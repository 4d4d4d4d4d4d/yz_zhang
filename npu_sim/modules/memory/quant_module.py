"""Quant: Quantization / Dequantization unit. Reference: SPEC-008 §3.

Single module bidirectional via `direction` config. Independent of DAGC
(which does BFP unpack — a pure format change) because Quant performs
real numerical scaling with per-tensor or per-channel scale tables.
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
from npu_sim.interfaces.services import IEventBus, IStatSink, StallReason
from npu_sim.interfaces.transport import (
    DataType,
    ITransportPort,
    PortDirection,
    PortSpec,
    TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


_VALID_DIRECTIONS = {"quant", "dequant"}


@ModuleRegistry.register
class Quant(IModule):

    @classmethod
    def module_type(cls) -> str:
        return "Quant"

    @classmethod
    def module_version(cls) -> str:
        return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string", "enum": ["quant", "dequant"],
                    "default": "quant",
                },
                "bits_in": {"type": "integer", "minimum": 1, "default": 32},
                "bits_out": {"type": "integer", "minimum": 1, "default": 8},
                "enable_per_channel": {"type": "boolean", "default": False},
                "symmetric": {"type": "boolean", "default": True},
            },
            "required": ["direction"],
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability(
                name="int8_to_fp32",
                description="SPEC-008 §3.2.2: dequantize int8 → fp32.",
                area_cost_um2=4_000.0,
                static_power_uw=3.0,
                dynamic_energy_pj=0.10,
            ),
            Capability(
                name="fp32_to_int8",
                description="SPEC-008 §3.2.2: quantize fp32 → int8.",
                area_cost_um2=4_000.0,
                static_power_uw=3.0,
                dynamic_energy_pj=0.15,
            ),
            Capability(
                name="per_tensor_scale",
                description="Single scale + zero_point for the whole tensor.",
                area_cost_um2=500.0,
                static_power_uw=0.5,
                dynamic_energy_pj=0.0,
            ),
            Capability(
                name="per_channel_scale",
                description="SPEC-008 §3.2.2: scale/zero_point per output channel.",
                area_cost_um2=4_000.0,    # LUT storage
                static_power_uw=2.0,
                dynamic_energy_pj=0.02,
            ),
            Capability(
                name="symmetric_quant",
                description="zero_point = 0 (symmetric).",
                area_cost_um2=0.0,
                static_power_uw=0.0,
                dynamic_energy_pj=0.0,
            ),
            Capability(
                name="asymmetric_quant",
                description="zero_point != 0 (asymmetric).",
                area_cost_um2=1_000.0,    # extra adder/subtractor path
                static_power_uw=0.5,
                dynamic_energy_pj=0.01,
            ),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("data_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 8),
            PortSpec("scale_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    # ============== Lifecycle ==============

    def __init__(self) -> None:
        self._owner_id: str = self.module_type()
        self._event_bus: Optional[IEventBus] = None
        self._stat_sink: Optional[IStatSink] = None
        self._clock: Optional[IClock] = None
        self._configured: bool = False
        self._direction: str = "quant"
        self._bits_in: int = 32
        self._bits_out: int = 8
        self._enable_per_channel: bool = False
        self._symmetric: bool = True
        self._active_caps: list[str] = []
        self._busy: bool = False
        self._stage: str = "idle"
        self._processed: int = 0
        self._data_in_port: Optional[TlmInputPort] = None
        self._data_out_port: Optional[TlmOutputPort] = None
        self._scale_port: Optional[TlmInputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, module_id: str) -> None:
        self._owner_id = module_id

    def bind_services(self, event_bus, stat_sink, clock) -> None:
        self._event_bus = event_bus
        self._stat_sink = stat_sink
        self._clock = clock

    def configure(self, config: dict) -> None:
        if self._configured:
            raise RuntimeError("Quant.configure() once only.")
        direction = config.get("direction", "quant")
        if direction not in _VALID_DIRECTIONS:
            raise ConfigurationError(
                f"Quant.direction must be one of {_VALID_DIRECTIONS}, got {direction!r}"
            )
        self._direction = direction
        self._bits_in = config.get("bits_in", 32)
        self._bits_out = config.get("bits_out", 8)
        self._enable_per_channel = config.get("enable_per_channel", False)
        self._symmetric = config.get("symmetric", True)

        # Direction-specific capability.
        self._active_caps = []
        if direction == "quant":
            self._active_caps.append("fp32_to_int8")
        else:
            self._active_caps.append("int8_to_fp32")
        self._active_caps.append(
            "per_channel_scale" if self._enable_per_channel else "per_tensor_scale"
        )
        self._active_caps.append(
            "symmetric_quant" if self._symmetric else "asymmetric_quant"
        )

        specs = {p.name: p for p in self.port_specs()}
        self._data_in_port = TlmInputPort(specs["data_in"], self._owner_id, self._clock)
        self._data_out_port = TlmOutputPort(
            specs["data_out"], self._owner_id, self._clock, self._stat_sink
        )
        self._scale_port = TlmInputPort(specs["scale_in"], self._owner_id, self._clock)
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self) -> None:
        self._busy = False
        self._stage = "idle"
        self._processed = 0

    def destroy(self) -> None:
        self._data_in_port = None
        self._data_out_port = None
        self._scale_port = None
        self._cmd_port = None

    def input_ports(self) -> dict[str, ITransportPort]:
        if not self._configured:
            return {}
        return {
            "data_in": self._data_in_port,
            "scale_in": self._scale_port,
            "cmd_in": self._cmd_port,
        }

    def output_ports(self) -> dict[str, ITransportPort]:
        return {"data_out": self._data_out_port} if self._data_out_port else {}

    def active_capabilities(self) -> list[str]:
        return list(self._active_caps)

    def can_execute(self, operation: IOperation) -> bool:
        return self._configured

    def estimate_latency(self, operation: IOperation) -> LatencyEstimate:
        # §3.4.1: 1 cycle/element + per-channel LUT extra.
        n = int(operation.shape_info.get("n_elements", 256))
        cycles = n + (1 if self._enable_per_channel else 0)
        return LatencyEstimate(
            min_cycles=cycles, typical_cycles=cycles,
            max_cycles=int(cycles * 1.1), confidence=0.7,
        )

    def estimate_energy(self, operation: IOperation) -> EnergyEstimate:
        n = int(operation.shape_info.get("n_elements", 256))
        per_elem = 0.15 if self._direction == "quant" else 0.10
        return EnergyEstimate(
            dynamic_pj=per_elem * n,
            static_pj_per_cycle=self.static_power_uw() * 1e-6,
            confidence=0.7,
        )

    def snapshot_state(self) -> ModuleState:
        return ModuleState(
            busy=self._busy,
            current_op=self._stage if self._busy else None,
            internal_fifo_levels={
                "data_in": self._data_in_port.fifo_level() if self._data_in_port else 0,
            },
        )

    @property
    def processed(self) -> int:
        return self._processed

    # ============== Behavior ==============

    def _scale_factor(self) -> int:
        """Output-to-input byte size ratio.
        - quant FP32→INT8: 1/4 → output size = input // 4
        - dequant INT8→FP32: 4× → output size = input * 4
        """
        if self._direction == "quant":
            return max(1, self._bits_out) // 8 or 1
        return max(1, self._bits_in) // 8 or 1

    def behavior(self) -> Iterator[None]:
        """§3.4 — each input token consumed in 1 + per_channel cycles,
        emitted with scaled byte width (quant shrinks, dequant expands).
        """
        while True:
            self._busy = False
            self._stage = "idle"
            if self._cmd_port is not None:
                self._cmd_port.try_receive()
            if self._scale_port is not None:
                self._scale_port.try_receive()  # opportunistic scale-table load

            token = self._data_in_port.try_receive()
            if token is None:
                yield
                continue

            self._busy = True
            self._stage = "load_scale" if self._enable_per_channel else (
                "quantize" if self._direction == "quant" else "dequantize"
            )
            if self._enable_per_channel:
                yield  # 1 cycle LUT lookup
                self._stage = "quantize" if self._direction == "quant" else "dequantize"

            # Per-element cycles (model as N bytes through the path).
            elems = max(1, token.size_bytes)
            for _ in range(elems):
                yield

            # Scale output width.
            if self._direction == "quant":
                out_size = max(1, token.size_bytes // 4)
            else:
                out_size = token.size_bytes * 4

            self._stage = "emit"
            out = TransportToken(
                payload=token.payload,
                size_bytes=out_size,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**token.metadata, "quantized": self._direction == "quant",
                          "dequantized": self._direction == "dequant"},
            )
            yield from self._data_out_port.send(out)
            self._processed += 1
