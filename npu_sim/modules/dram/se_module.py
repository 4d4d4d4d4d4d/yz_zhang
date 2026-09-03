"""SE: Sparse Engine. SPEC-011 §3."""

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
class SE(IModule):

    @classmethod
    def module_type(cls) -> str: return "SE"
    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "sparsity_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0, "default": 0.5},
                "enable_structured_pruning": {"type": "boolean", "default": False},
                "element_bytes": {"type": "integer", "minimum": 1, "default": 4},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("sparse_skip_zero", "Skip-zero compute.", 22_000.0, 12.0, 0.2),
            Capability("sparse_index_decode", "Decode sparse index.", 0.0, 0.0, 0.05),
            Capability("structured_pruning_support", "N:M structured prune.", 8_000.0, 4.0, 0.1),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("sparse_in", PortDirection.INPUT, DataType.DATA, 256, 8),
            PortSpec("dense_out", PortDirection.OUTPUT, DataType.DATA, 256, 8),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._sparsity = 0.5; self._structured = False; self._elem_bytes = 4
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._processed = 0
        self._in_port = None; self._out_port = None; self._cmd_port = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock):
        self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("SE.configure() once.")
        self._sparsity = config.get("sparsity_ratio", 0.5)
        self._structured = config.get("enable_structured_pruning", False)
        self._elem_bytes = config.get("element_bytes", 4)
        self._active_caps = ["sparse_skip_zero", "sparse_index_decode"]
        if self._structured:
            self._active_caps.append("structured_pruning_support")
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["sparse_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["dense_out"], self._owner_id, self._clock, self._stat_sink)
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._processed = 0
    def destroy(self): self._in_port = self._out_port = self._cmd_port = None
    def input_ports(self):
        return {"sparse_in": self._in_port, "cmd_in": self._cmd_port} if self._configured else {}
    def output_ports(self): return {"dense_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return self._configured

    def estimate_latency(self, op):
        n = int(op.shape_info.get("n_elements", 256))
        nnz = max(1, int(n * (1.0 - self._sparsity)))
        if self._structured:
            nnz = int(nnz * 0.7)  # structured prune efficiency
        return LatencyEstimate(nnz, nnz, int(nnz * 1.2), 0.7)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("n_elements", 256))
        nnz = max(1, int(n * (1.0 - self._sparsity)))
        return EnergyEstimate(0.2 * nnz, self.static_power_uw()*1e-6, 0.7)

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            if self._cmd_port: self._cmd_port.try_receive()
            tok = self._in_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "decode_mask"; yield
            self._stage = "skip_zero"
            elems = max(1, tok.size_bytes // self._elem_bytes)
            nnz = max(1, int(elems * (1.0 - self._sparsity)))
            if self._structured:
                nnz = max(1, int(nnz * 0.7))
            for _ in range(max(0, nnz - 1)):
                yield
            self._stage = "emit_dense"
            out = TransportToken(
                payload=tok.payload,
                size_bytes=max(1, nnz * self._elem_bytes),
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "se_skipped_zeros": int(elems - nnz)},
            )
            yield from self._out_port.send(out)
            self._processed += 1
