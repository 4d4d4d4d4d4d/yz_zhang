"""CDE: Compression / Decompression Engine. SPEC-009 §4."""

from __future__ import annotations

from typing import Iterator, Optional

from npu_sim.core.errors import ConfigurationError
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import (
    AreaModel, Capability, EnergyEstimate, IModule, LatencyEstimate, ModuleState,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.transport import (
    DataType, ITransportPort, PortDirection, PortSpec, TransportToken,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort


_VALID_DIRECTIONS = {"compress", "decompress"}


@ModuleRegistry.register
class CDE(IModule):

    @classmethod
    def module_type(cls) -> str: return "CDE"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["compress", "decompress"], "default": "compress"},
                "compression_ratio": {"type": "number", "minimum": 0.05, "maximum": 1.0, "default": 0.5},
                "enable_zlib": {"type": "boolean", "default": False},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("compress_rle", "RLE encode.", 20_000.0, 12.0, 0.6),
            Capability("decompress_rle", "RLE decode.", 20_000.0, 12.0, 0.6),
            Capability("compress_zlib", "zlib encode.", 30_000.0, 18.0, 1.0),
            Capability("decompress_zlib", "zlib decode.", 30_000.0, 18.0, 1.0),
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
        self._direction = "compress"; self._ratio = 0.5; self._enable_zlib = False
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._processed = 0
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("CDE.configure() once.")
        d = config.get("direction", "compress")
        if d not in _VALID_DIRECTIONS:
            raise ConfigurationError(f"CDE.direction must be in {_VALID_DIRECTIONS}, got {d!r}")
        self._direction = d
        self._ratio = config.get("compression_ratio", 0.5)
        self._enable_zlib = config.get("enable_zlib", False)
        algo = "zlib" if self._enable_zlib else "rle"
        self._active_caps = [f"{d}_{algo}"]
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["data_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["data_out"], self._owner_id, self._clock, self._stat_sink)
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._processed = 0
    def destroy(self): self._in_port = self._out_port = self._cmd_port = None
    def input_ports(self):
        return {"data_in": self._in_port, "cmd_in": self._cmd_port} if self._configured else {}
    def output_ports(self): return {"data_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        n = int(op.shape_info.get("n_elements", 256))
        cycles = max(1, n // 2)
        return LatencyEstimate(cycles, cycles, int(cycles*1.2), 0.7)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("n_elements", 256))
        per_byte = 1.0 if self._enable_zlib else 0.6
        return EnergyEstimate(per_byte * n, self.static_power_uw()*1e-6, 0.7)

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            if self._cmd_port: self._cmd_port.try_receive()
            tok = self._in_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True
            self._stage = "encode" if self._direction == "compress" else "decode"
            cycles = max(1, tok.size_bytes // 2)
            for _ in range(cycles):
                yield
            self._stage = "emit"
            if self._direction == "compress":
                out_size = max(1, int(tok.size_bytes * self._ratio))
            else:
                out_size = max(1, int(tok.size_bytes / max(0.05, self._ratio)))
            out = TransportToken(
                payload=tok.payload, size_bytes=out_size,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "cde_direction": self._direction},
            )
            yield from self._out_port.send(out)
            self._processed += 1
