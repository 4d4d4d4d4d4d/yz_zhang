"""Architecture Elaborator: 9-phase DSL → IArchitecture pipeline.

Reference: SPEC-003 §5.

Phases:
  1.   Load + merge (load_dsl)
  2.   JSON Schema validation
  3.   Semantic validation
  3.5. Cross-module config consistency (warn, R6#9)
  4.   Instantiate clocks
  5.   Instantiate modules
  6.   Build connections (with CDC detection)
  7.   Build topology
  8.   Validate constraints
  9.   Return IArchitecture
"""

from __future__ import annotations

from typing import Callable, Optional

import jsonschema

from npu_sim.architecture.architecture import (
    Architecture,
    ElaboratedConnection,
    ElaboratedTopology,
    IArchitecture,
)
from npu_sim.architecture.clock import SimpleClock
from npu_sim.architecture.dsl_schema import DSL_SCHEMA
from npu_sim.architecture.loader import load_dsl
from npu_sim.core.errors import (
    InvalidMappingHintError,
    OverrideError,
    PortNotFoundError,
    UnknownModuleTypeError,
)
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.interfaces.module import IModule
from npu_sim.interfaces.services import IEventBus, IStatSink, InMemoryEventBus, InMemoryStatSink
from npu_sim.interfaces.transport import (
    CdcConnectionSpec,
    ConnectionSpec,
    PortDirection,
)


# Type alias for the consistency-rule hook (Phase 3.5).
ConsistencyRule = Callable[[dict], Optional[str]]


def _apply_relocate(module: IModule, reloc: dict) -> None:
    """Wrap a module's estimate_* methods with __relocate__ multipliers.

    SPEC-003 v1.1 §2.2 — multipliers apply on top of the module's own
    estimate so capability changes are not required. The original methods
    are preserved on ``module._relocate_original_*`` for inspection.
    """
    from npu_sim.interfaces.module import AreaModel

    lat_pct = reloc.get("latency_penalty_pct", 0.0)
    nrg_pct = reloc.get("energy_penalty_pct", 0.0)
    area_pct = reloc.get("area_penalty_pct", 0.0)

    if lat_pct == 0.0 and nrg_pct == 0.0 and area_pct == 0.0:
        return  # nothing to do; pure-tagging relocate.

    lat_factor = 1.0 + lat_pct / 100.0
    nrg_factor = 1.0 + nrg_pct / 100.0
    area_factor = 1.0 + area_pct / 100.0

    orig_latency = module.estimate_latency
    orig_energy = module.estimate_energy
    orig_area = module.estimate_area

    def relocated_latency(op):
        est = orig_latency(op)
        return type(est)(
            min_cycles=int(est.min_cycles * lat_factor),
            typical_cycles=int(est.typical_cycles * lat_factor),
            max_cycles=int(est.max_cycles * lat_factor),
            confidence=est.confidence,
        )

    def relocated_energy(op):
        est = orig_energy(op)
        return type(est)(
            dynamic_pj=est.dynamic_pj * nrg_factor,
            static_pj_per_cycle=est.static_pj_per_cycle * nrg_factor,
            confidence=est.confidence,
        )

    def relocated_area():
        a = orig_area()
        return AreaModel(
            um2=a.um2 * area_factor,
            breakdown={k: v * area_factor for k, v in a.breakdown.items()},
            notes=(a.notes + " | __relocate__").strip(" |"),
        )

    # Stash originals for invariant / inspection.
    module._relocate_original_estimate_latency = orig_latency
    module._relocate_original_estimate_energy = orig_energy
    module._relocate_original_estimate_area = orig_area
    module._relocate_meta = dict(reloc)
    module.estimate_latency = relocated_latency
    module.estimate_energy = relocated_energy
    module.estimate_area = relocated_area

    # total_area_um2 is what runner.run_simulation aggregates; override too.
    def relocated_total_area_um2() -> float:
        return relocated_area().um2

    module.total_area_um2 = relocated_total_area_um2


class ArchitectureElaborator:
    """Translate a DSL description into an in-memory Architecture object."""

    def __init__(
        self,
        registry: ModuleRegistry = ModuleRegistry,
        event_bus: Optional[IEventBus] = None,
        stat_sink: Optional[IStatSink] = None,
        consistency_rules: Optional[list[ConsistencyRule]] = None,
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus or InMemoryEventBus()
        self._stat_sink = stat_sink or InMemoryStatSink(event_bus=self._event_bus)
        self._consistency_rules = list(consistency_rules or [])

    def elaborate(self, dsl_path: str) -> IArchitecture:
        # ============== Phase 1: load + merge ==============
        merged, load_warnings = load_dsl(dsl_path)

        # ============== Phase 2: schema validation ==============
        jsonschema.validate(merged, DSL_SCHEMA)

        # ============== Phase 3: semantic validation ==============
        self._validate_semantics(merged)

        # ============== Phase 3.5: config-consistency warnings ==============
        consistency_warnings = self._check_consistency(merged)
        warnings = list(load_warnings) + consistency_warnings

        # ============== Phase 4: instantiate clocks ==============
        clocks = self._instantiate_clocks(merged)

        # ============== Phase 5: instantiate modules ==============
        modules = self._instantiate_modules(merged, clocks)

        # ============== Phase 6: build connections (with CDC detection) ==============
        connections = self._build_connections(merged, modules, clocks)

        # ============== Phase 7: build topology ==============
        topology = self._build_topology(merged)

        # ============== Phase 8: validate constraints ==============
        self._validate_constraints(merged, modules, warnings)

        # ============== Phase 9: return ==============
        return Architecture(
            _name=merged.get("name", "unnamed"),
            _metadata=merged.get("metadata", {}),
            _modules=modules,
            _connections=connections,
            _clocks=clocks,
            _topology=topology,
            _mapping_hints=merged.get("mapping_hints", {}),
            _warnings=warnings,
        )

    # ============================================================
    # Phase 3: semantic validation
    # ============================================================

    def _validate_semantics(self, merged: dict) -> None:
        # 3a: module types must be registered
        registered = set(self._registry.list_modules())
        for inst in merged.get("modules", []):
            if inst["type"] not in registered:
                raise UnknownModuleTypeError(
                    f"Module instance {inst['id']!r} references unknown "
                    f"module_type {inst['type']!r}. "
                    f"Registered: {sorted(registered)}."
                )

        # 3b: clock refs must exist
        clock_ids = {cd["id"] for cd in merged.get("clock_domains", [])}
        for inst in merged.get("modules", []):
            cref = inst.get("clock")
            if cref is not None and cref not in clock_ids:
                raise OverrideError(
                    f"Module {inst['id']!r} references unknown clock "
                    f"domain {cref!r}. Available: {sorted(clock_ids)}."
                )

        # 3c: connection endpoints must reference existing modules + port_specs
        modules_by_id = {m["id"]: m for m in merged.get("modules", [])}
        for c in merged.get("connections", []):
            src_mod_id, src_port = c["from"].split(".")
            dst_mod_id, dst_port = c["to"].split(".")

            for mod_id in (src_mod_id, dst_mod_id):
                if mod_id not in modules_by_id:
                    raise PortNotFoundError(
                        f"Connection {c['from']} → {c['to']} references "
                        f"unknown module {mod_id!r}."
                    )

            src_cls = self._registry._registry[modules_by_id[src_mod_id]["type"]]
            dst_cls = self._registry._registry[modules_by_id[dst_mod_id]["type"]]

            src_specs = {p.name: p for p in src_cls.port_specs()}
            dst_specs = {p.name: p for p in dst_cls.port_specs()}

            if src_port not in src_specs:
                raise PortNotFoundError(
                    f"Connection {c['from']} → {c['to']}: source port "
                    f"{src_port!r} not declared on {src_cls.module_type()}. "
                    f"Available: {sorted(src_specs)}."
                )
            if dst_port not in dst_specs:
                raise PortNotFoundError(
                    f"Connection {c['from']} → {c['to']}: sink port "
                    f"{dst_port!r} not declared on {dst_cls.module_type()}. "
                    f"Available: {sorted(dst_specs)}."
                )

            if src_specs[src_port].direction != PortDirection.OUTPUT:
                raise PortNotFoundError(
                    f"Connection {c['from']} → {c['to']}: source port "
                    f"{src_port!r} must be an OUTPUT port."
                )
            if dst_specs[dst_port].direction != PortDirection.INPUT:
                raise PortNotFoundError(
                    f"Connection {c['from']} → {c['to']}: sink port "
                    f"{dst_port!r} must be an INPUT port."
                )

        # 3d: mapping_hints reachability (D2)
        hints = merged.get("mapping_hints", {})
        if hints:
            module_ids = set(modules_by_id)
            for op_type, stages in hints.items():
                for stage_name, target in stages.items():
                    targets = target if isinstance(target, list) else [target]
                    for tid in targets:
                        if tid not in module_ids:
                            raise InvalidMappingHintError(
                                f"mapping_hints[{op_type!r}][{stage_name!r}] "
                                f"references unknown module {tid!r}. "
                                f"Available: {sorted(module_ids)}."
                            )

        # 3e: topology.dies must reference existing modules
        topology = merged.get("topology", {})
        if topology:
            module_ids = set(modules_by_id)
            for die in topology.get("dies", []):
                for mid in die.get("modules", []):
                    if mid not in module_ids:
                        raise OverrideError(
                            f"Topology die {die['id']!r} references unknown "
                            f"module {mid!r}."
                        )

    # ============================================================
    # Phase 3.5: cross-module config consistency
    # ============================================================

    def _check_consistency(self, merged: dict) -> list[str]:
        warnings: list[str] = []
        for rule in self._consistency_rules:
            msg = rule(merged)
            if msg:
                warnings.append(msg)
        return warnings

    # ============================================================
    # Phase 4: clocks
    # ============================================================

    def _instantiate_clocks(self, merged: dict) -> dict[str, SimpleClock]:
        return {
            cd["id"]: SimpleClock(domain_id=cd["id"], period_ps=cd["period_ps"])
            for cd in merged.get("clock_domains", [])
        }

    # ============================================================
    # Phase 5: modules
    # ============================================================

    def _instantiate_modules(
        self,
        merged: dict,
        clocks: dict[str, SimpleClock],
    ) -> dict[str, IModule]:
        # If no clock_domains were declared (minimal test fixtures), accept
        # implicit assignment to the first / only clock.
        modules: dict[str, IModule] = {}
        for inst in merged.get("modules", []):
            cfg = inst.get("config", {})
            module = self._registry.create(inst["type"], cfg)

            clock_ref = inst.get("clock")
            if clock_ref is None and clocks:
                clock_ref = next(iter(clocks))
            elif clock_ref is None and not clocks:
                # Synthesize a fallback for test fixtures without clock_domains.
                clocks["_default"] = SimpleClock("_default", period_ps=1000)
                clock_ref = "_default"

            # Convention (pending v1.1 spec amendment): if the module exposes
            # `assign_id`, the Elaborator passes the DSL instance id so the
            # module can use it as owner_module on its ports and stall records.
            if hasattr(module, "assign_id"):
                module.assign_id(inst["id"])

            module.bind_services(
                event_bus=self._event_bus,
                stat_sink=self._stat_sink,
                clock=clocks[clock_ref],
            )
            module.configure(cfg)

            # SPEC-003 v1.1 §2.2: __relocate__ wraps estimate_* with penalty
            # multipliers. Applied here so any consumer of estimate_latency /
            # estimate_energy / estimate_area sees the relocated coefficients.
            reloc = inst.get("__relocate__")
            if reloc:
                _apply_relocate(module, reloc)

            modules[inst["id"]] = module
        return modules

    # ============================================================
    # Phase 6: connections (with SPEC-002 §5.1 CDC detection)
    # ============================================================

    def _build_connections(
        self,
        merged: dict,
        modules: dict[str, IModule],
        clocks: dict[str, SimpleClock],
    ) -> list[ElaboratedConnection]:
        modules_by_id = {m["id"]: m for m in merged.get("modules", [])}
        connections: list[ElaboratedConnection] = []

        for c in merged.get("connections", []):
            src_mod_id, src_port = c["from"].split(".")
            dst_mod_id, dst_port = c["to"].split(".")

            src_clock_id = modules_by_id[src_mod_id].get("clock")
            dst_clock_id = modules_by_id[dst_mod_id].get("clock")
            src_clock = clocks.get(src_clock_id) if src_clock_id else None
            dst_clock = clocks.get(dst_clock_id) if dst_clock_id else None
            is_cross_domain = (
                src_clock is not None
                and dst_clock is not None
                and not src_clock.is_same_domain(dst_clock)
            )

            base_spec_kwargs = dict(
                source_module=src_mod_id,
                source_port=src_port,
                sink_module=dst_mod_id,
                sink_port=dst_port,
                fifo_depth=c.get("fifo_depth", 1),
                latency_cycles=c.get("latency_cycles", 1),
                bandwidth_gbps=c.get("bandwidth_gbps", 0.0),
            )

            if is_cross_domain:
                spec: ConnectionSpec = CdcConnectionSpec(
                    **base_spec_kwargs,
                    source_domain=src_clock.domain_id,
                    sink_domain=dst_clock.domain_id,
                )
            else:
                spec = ConnectionSpec(**base_spec_kwargs)

            # Optionally wire real TlmConnection + port attach. Modules that
            # don't yet expose runtime ports (e.g. Dummy) are skipped — only
            # the spec is recorded for them.
            runtime = self._maybe_wire_connection(
                spec=spec,
                source_module=modules[src_mod_id],
                source_port_name=src_port,
                sink_module=modules[dst_mod_id],
                sink_port_name=dst_port,
                source_clock=src_clock or next(iter(self._instance_clocks(clocks))),
            )

            connections.append(
                ElaboratedConnection(
                    spec=spec,
                    source_module=modules[src_mod_id],
                    sink_module=modules[dst_mod_id],
                    is_cross_domain=is_cross_domain,
                    runtime=runtime,
                )
            )
        return connections

    @staticmethod
    def _instance_clocks(clocks):
        return clocks.values()

    def _maybe_wire_connection(
        self,
        spec,
        source_module,
        source_port_name,
        sink_module,
        sink_port_name,
        source_clock,
    ):
        """Build a TlmConnection and attach() both ports if they support it."""
        from npu_sim.runtime.connection import TlmConnection
        from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort

        out_ports = source_module.output_ports()
        in_ports = sink_module.input_ports()
        out_port = out_ports.get(source_port_name)
        in_port = in_ports.get(sink_port_name)

        if not isinstance(out_port, TlmOutputPort) or not isinstance(in_port, TlmInputPort):
            return None

        conn = TlmConnection(spec=spec, source_clock=source_clock)
        out_port.attach(conn, sink_module_id=getattr(sink_module, "_owner_id", sink_module.module_type()))
        in_port.attach(conn)
        return conn

    # ============================================================
    # Phase 7: topology
    # ============================================================

    def _build_topology(self, merged: dict) -> Optional[ElaboratedTopology]:
        t = merged.get("topology")
        if not t:
            return None
        return ElaboratedTopology(
            type=t["type"],
            dies=list(t.get("dies", [])),
            inter_die=list(t.get("inter_die", [])),
        )

    # ============================================================
    # Phase 8: constraints
    # ============================================================

    def _validate_constraints(
        self,
        merged: dict,
        modules: dict[str, IModule],
        warnings: list[str],
    ) -> None:
        constraints = merged.get("constraints", {})
        if not constraints:
            return

        total_area_um2 = sum(m.total_area_um2() for m in modules.values())
        total_area_mm2 = total_area_um2 / 1e6

        total_static_uw = sum(m.static_power_uw() for m in modules.values())
        total_static_w = total_static_uw / 1e6

        # Apply max/min where declared. Violations become warnings (not errors)
        # so an architect can still elaborate an out-of-budget design and
        # iterate on it; reports will surface the warning.
        checks: list[tuple[str, float]] = [
            ("total_area_mm2", total_area_mm2),
            ("total_static_power_w", total_static_w),
        ]
        for name, actual in checks:
            spec = constraints.get(name)
            if not spec:
                continue
            if "max" in spec and actual > spec["max"]:
                warnings.append(
                    f"Constraint violated: {name} = {actual:.3f} exceeds max {spec['max']}."
                )
            if "min" in spec and actual < spec["min"]:
                warnings.append(
                    f"Constraint violated: {name} = {actual:.3f} below min {spec['min']}."
                )
