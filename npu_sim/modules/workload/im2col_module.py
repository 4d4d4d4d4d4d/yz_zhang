"""IM2COL: convolution → GEMM tensor reorder. SPEC-009 §1."""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel, Capability, EnergyEstimate, IModule, LatencyEstimate, ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.transport import (
    DataType, ITransportPort, PortDirection, PortSpec, TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


@ModuleRegistry.register
class IM2COL(IModule):

    @classmethod
    def module_type(cls) -> str: return "IM2COL"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "kernel_h": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
                "kernel_w": {"type": "integer", "minimum": 1, "maximum": 7, "default": 3},
                "stride": {"type": "integer", "minimum": 1, "default": 1},
                "enable_stride_dilation": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("conv2col_reorder", "Conv → GEMM reshape.", 18_000.0, 12.0, 0.3),
            Capability("stride_dilation", "Stride/dilation support.", 4_000.0, 3.0, 0.05),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("act_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("kernel_desc_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
            PortSpec("im2col_out", PortDirection.OUTPUT, DataType.DATA, 512, 8),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type()
        self._configured = False
        self._kh, self._kw, self._stride = 3, 3, 1
        self._enable_dilation = False
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"
        self._unrolled = 0
        self._in_port: Optional[TlmInputPort] = None
        self._kdesc_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("IM2COL.configure() once.")
        self._kh = config.get("kernel_h", 3)
        self._kw = config.get("kernel_w", 3)
        self._stride = config.get("stride", 1)
        self._enable_dilation = config.get("enable_stride_dilation", False)
        self._active_caps = ["conv2col_reorder"]
        if self._enable_dilation:
            self._active_caps.append("stride_dilation")
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["act_in"], self._owner_id, self._clock)
        self._kdesc_port = TlmInputPort(specs["kernel_desc_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["im2col_out"], self._owner_id, self._clock, self._stat_sink)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._unrolled = 0
    def destroy(self): self._in_port = self._out_port = self._kdesc_port = None
    def input_ports(self):
        return {"act_in": self._in_port, "kernel_desc_in": self._kdesc_port} if self._configured else {}
    def output_ports(self):
        return {"im2col_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op: IOperation) -> LatencyEstimate:
        cycles = self._kh * self._kw
        return LatencyEstimate(cycles, cycles, int(cycles*1.2), 0.7)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("n_elements", 256))
        return EnergyEstimate(0.3 * n * self._kh * self._kw, self.static_power_uw()*1e-6, 0.7)

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        per_tok = max(1, self._kh * self._kw)
        while True:
            self._busy = False; self._stage = "idle"
            if self._kdesc_port: self._kdesc_port.try_receive()
            tok = self._in_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "load_act"; yield
            self._stage = "unroll"
            for _ in range(per_tok - 1):
                yield
            self._stage = "emit"
            out = TransportToken(
                payload=tok.payload,
                size_bytes=tok.size_bytes * self._kh * self._kw,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "im2col": True, "kh": self._kh, "kw": self._kw},
            )
            yield from self._out_port.send(out)
            self._unrolled += 1
