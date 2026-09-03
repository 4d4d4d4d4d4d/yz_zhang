"""RDC: Reduction Unit (tree-reduce sum/max). SPEC-009 §2."""

from __future__ import annotations

import math
from typing import Iterator, Optional

from npu_sim import physical
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
class RDC(IModule):

    @classmethod
    def module_type(cls) -> str: return "RDC"

    @classmethod
    def module_version(cls) -> str: return "1.0.0"

    @classmethod
    def config_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "tree_width": {"type": "integer", "minimum": 2, "maximum": 64, "default": 8},
                "mode": {"type": "string", "enum": ["sum", "max"], "default": "sum"},
                "element_bytes": {"type": "integer", "minimum": 1, "default": 4},
            },
        }

    @classmethod
    def declared_capabilities(cls) -> list[Capability]:
        return [
            Capability("row_reduce_sum", "Sum reduction.", 6_000.0, 4.0, 0.4),
            Capability("row_reduce_max", "Max reduction.", 6_000.0, 4.0, 0.4),
            Capability("tree_reduction", "Log-depth tree.", 0.0, 0.0, 0.0),
        ]

    @classmethod
    def port_specs(cls) -> list[PortSpec]:
        return [
            PortSpec("vec_in", PortDirection.INPUT, DataType.DATA, 512, 8),
            PortSpec("reduced_out", PortDirection.OUTPUT, DataType.DATA, 64, 4),
            PortSpec("cmd_in", PortDirection.INPUT, DataType.COMMAND, 64, 4),
        ]

    def __init__(self) -> None:
        self._owner_id = self.module_type(); self._configured = False
        self._tree_width = 8; self._mode = "sum"; self._elem_bytes = 4
        self._active_caps: list[str] = []
        self._busy = False; self._stage = "idle"; self._reduced = 0
        self._in_port: Optional[TlmInputPort] = None
        self._out_port: Optional[TlmOutputPort] = None
        self._cmd_port: Optional[TlmInputPort] = None

    def assign_id(self, m): self._owner_id = m
    def bind_services(self, event_bus, stat_sink, clock): self._event_bus, self._stat_sink, self._clock = event_bus, stat_sink, clock

    def configure(self, config: dict) -> None:
        if self._configured: raise RuntimeError("RDC.configure() once.")
        self._tree_width = config.get("tree_width", 8)
        self._mode = config.get("mode", "sum")
        self._elem_bytes = config.get("element_bytes", 4)
        self._active_caps = ["tree_reduction"]
        self._active_caps.append("row_reduce_sum" if self._mode == "sum" else "row_reduce_max")
        specs = {p.name: p for p in self.port_specs()}
        self._in_port = TlmInputPort(specs["vec_in"], self._owner_id, self._clock)
        self._out_port = TlmOutputPort(specs["reduced_out"], self._owner_id, self._clock, self._stat_sink)
        self._cmd_port = TlmInputPort(specs["cmd_in"], self._owner_id, self._clock)
        self._configured = True

    def reset(self): self._busy = False; self._stage = "idle"; self._reduced = 0
    def destroy(self): self._in_port = self._out_port = self._cmd_port = None
    def input_ports(self): return {"vec_in": self._in_port, "cmd_in": self._cmd_port} if self._configured else {}
    def output_ports(self): return {"reduced_out": self._out_port} if self._out_port else {}
    def active_capabilities(self): return list(self._active_caps)
    def can_execute(self, op): return True

    def estimate_latency(self, op):
        n = int(op.shape_info.get("n_elements", 8))
        depth = max(1, int(math.ceil(math.log2(max(2, n)))))
        return LatencyEstimate(depth + 1, depth + 1, int((depth+1)*1.2), 0.8)

    def estimate_energy(self, op):
        n = int(op.shape_info.get("n_elements", 8))
        return EnergyEstimate(0.4 * n, self.static_power_uw()*1e-6, 0.7)

    def estimate_area(self):
        # SPEC-013: FP reduction tree of tree_width inputs = width-1 FP adders.
        storage = physical.reduction_tree_area_um2(self._tree_width)
        bd = {c.name: c.area_cost_um2 for c in self.declared_capabilities() if c.name in self._active_caps}
        bd["tree_adders"] = storage
        return AreaModel(um2=sum(bd.values()), breakdown=bd,
                         notes=f"SPEC-013 physical @{physical.REFERENCE_NODE_NM}nm FP reduction tree")

    def total_area_um2(self): return self.estimate_area().um2

    def snapshot_state(self):
        return ModuleState(busy=self._busy, current_op=self._stage if self._busy else None)

    def behavior(self) -> Iterator[None]:
        while True:
            self._busy = False; self._stage = "idle"
            if self._cmd_port: self._cmd_port.try_receive()
            tok = self._in_port.try_receive()
            if tok is None:
                yield; continue
            self._busy = True; self._stage = "load_vec"; yield
            n_elems = max(2, tok.size_bytes // max(1, self._elem_bytes))
            depth = max(1, int(math.ceil(math.log2(n_elems))))
            self._stage = "reduce_log2"
            for _ in range(depth):
                yield
            self._stage = "emit"
            out = TransportToken(
                payload=tok.payload, size_bytes=self._elem_bytes,
                timestamp_ps=self._clock.current_time_ps(),
                source_module=self._owner_id,
                metadata={**tok.metadata, "rdc_mode": self._mode},
            )
            yield from self._out_port.send(out)
            self._reduced += 1
