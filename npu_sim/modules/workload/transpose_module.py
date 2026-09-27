"""Transpose: tensor layout flip. SPEC-009 §5."""

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
class Transpose(IModule):

    @classmethod
    def module_type(cls) -> str: return "Transpose"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "enable_3d": {"type": "boolean", "default": False},
                "element_bytes": {"type": "integer", "minimum": 1, "default": 4},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("layout_transform_2d", "2D transpose.", 10_000.0, 6.0, 0.1),
            Capability("layout_transform_3d", "3D permute.", 5_000.0, 3.0, 0.05),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("data_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("data_out", PortDirection.OUTPUT, DataType.DATA, 256, 8),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._enable_3d = False; self._elem_bytes = 4
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._transposed = 0
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("Transpose.configure() once.")
        self._enable_3d = config.get("enable_3d", False)
        self._elem_bytes = config.get("element_bytes", 4)
        self._active_caps = ["layout_transform_2d"]
        if self._enable_3d:
            self._active_caps.append("layout_transform_3d")
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["data_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["data_out"], self._owner_id, self._clock, self._stat_sink)
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._transposed = 0
    def destroy(self): self._in_port = self._out_port = self._cmd_port = None
    def input_ports(self):
        return {"data_in": self._in_port, "cmd_in": self._cmd_port} if self._configured else {}
    def output_ports(self): return {"data_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        n = int(op.shape_info.get("n_elements", 64))
        return LatencyEstimate(n, n, int(n*1.1), 0.8)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("n_elements", 64))
        return EnergyEstimate(0.1 * n, self.static_power_uw()*1e-6, 0.8)

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            if self._cmd_port: self._cmd_port.try_receive()
            tok = self._in_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "read_in"; yield
            self._stage = "transpose"
            elems = max(1, tok.size_bytes // self._elem_bytes)
            for _ in range(max(0, elems - 1)):
                yield
            self._stage = "emit"
            out = TransportToken(
                payload=tok.payload, size_bytes=tok.size_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "transposed": True, "is_3d": self._enable_3d},
            )
            yield from self._out_port.send(out)
            self._transposed += 1
