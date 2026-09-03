"""Full-chip state snapshot — the feasible subset of QEMU-style savevm.

QEMU roadmap item #4 (docs/QEMU-Benchmark-Analysis.md §3.2) asked for
checkpoint/restore: freeze the whole simulation at cycle N, then resume N
variants from that point. In this Python runtime **binary restore is
structurally blocked** — each module's in-flight timing lives in a
long-lived generator frame (e.g. MAC's ``for _ in range(fill_n): yield``
countdown), which ``snapshot_state()`` does not expose and Python cannot
pickle. Resuming mid-operation would require rewriting every ``behavior()``
into an explicit externalised state machine, a Phase-5-scale change
ADR-001.1 already defers to the SystemC kernel (which is natively
event-driven and check-pointable). See the finding in docs/specs/README.md.

What *is* both feasible and useful today is the read-only half — savevm's
*data view* without loadvm: capture every module's ``snapshot_state()`` plus
every connection's FIFO occupancy and the clock at a chosen cycle. And
because the runtime is now fully deterministic (SPEC / §3.3 RNG removal),
"restore to cycle N" is available for free as *deterministic replay*: two
independent runs reach a field-identical :class:`StateSnapshot` at the same
cycle. Re-running to a warmup point costs ~microseconds/cycle, so on this
platform replay is the honest, zero-risk substitute for a binary checkpoint.

This module provides the capture + a replay-to-cycle helper. It is pure
read-over-elaborated-arch: no module construction, no ``estimate_*`` calls,
so it stays inside the YAML-driven evaluation contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.runtime.connection import TlmConnection


@dataclass(frozen=True)
class ModuleSnapshot:
    """Point-in-time state of one module (from SPEC-001 §3.1 ModuleState)."""

    module_id: str
    module_type: str
    busy: bool
    current_op: Optional[str]
    internal_fifo_levels: tuple[tuple[str, int], ...]
    last_stall_reason: Optional[str]


@dataclass(frozen=True)
class ConnectionSnapshot:
    """Point-in-time occupancy of one TLM connection FIFO (SPEC-002)."""

    key: str
    in_flight: int
    capacity: int
    utilization: float
    tokens_dequeued: int


@dataclass(frozen=True)
class StateSnapshot:
    """Whole-chip state at a single cycle — the read-only savevm data view.

    Field-comparable across runs: two deterministic runs sampled at the same
    cycle produce equal snapshots (the replay-restore property).
    """

    architecture_name: str
    cycle: int
    time_ps: int
    modules: tuple[ModuleSnapshot, ...]
    connections: tuple[ConnectionSnapshot, ...]

    def busy_modules(self) -> tuple[str, ...]:
        return tuple(m.module_id for m in self.modules if m.busy)

    def total_in_flight(self) -> int:
        return sum(c.in_flight for c in self.connections)


@dataclass(frozen=True)
class FieldDiff:
    """One field that differs between two snapshots' matching entities."""

    entity: str          # module_id or connection key
    field: str
    value_a: object
    value_b: object


@dataclass(frozen=True)
class SnapshotDiff:
    """Structural diff of two whole-chip snapshots at the same cycle.

    The `compare` command diffs only aggregate metrics; this diffs the
    *internal* state so an A/B pair (same topology, different params) can be
    inspected for exactly where — which module stage, which FIFO — the two
    runs diverge at a chosen cycle.
    """

    cycle_a: int
    cycle_b: int
    name_a: str
    name_b: str
    only_in_a: tuple[str, ...]          # module_ids present only in A
    only_in_b: tuple[str, ...]
    module_diffs: tuple[FieldDiff, ...]
    connection_diffs: tuple[FieldDiff, ...]

    @property
    def identical(self) -> bool:
        return not (
            self.only_in_a or self.only_in_b
            or self.module_diffs or self.connection_diffs
        )


def diff_snapshots(a: StateSnapshot, b: StateSnapshot) -> SnapshotDiff:
    """Diff two snapshots field-by-field, matching modules by id and
    connections by key. Entities present in only one side are reported
    separately; the rest yield a :class:`FieldDiff` per differing field.
    """
    a_mods = {m.module_id: m for m in a.modules}
    b_mods = {m.module_id: m for m in b.modules}
    only_a = tuple(sorted(set(a_mods) - set(b_mods)))
    only_b = tuple(sorted(set(b_mods) - set(a_mods)))

    mod_diffs: list[FieldDiff] = []
    for mid in sorted(set(a_mods) & set(b_mods)):
        ma, mb = a_mods[mid], b_mods[mid]
        for field in ("busy", "current_op", "internal_fifo_levels", "last_stall_reason"):
            va, vb = getattr(ma, field), getattr(mb, field)
            if va != vb:
                mod_diffs.append(FieldDiff(mid, field, va, vb))

    a_conns = {c.key: c for c in a.connections}
    b_conns = {c.key: c for c in b.connections}
    conn_diffs: list[FieldDiff] = []
    for key in sorted(set(a_conns) & set(b_conns)):
        ca, cb = a_conns[key], b_conns[key]
        for field in ("in_flight", "utilization", "tokens_dequeued"):
            va, vb = getattr(ca, field), getattr(cb, field)
            if va != vb:
                conn_diffs.append(FieldDiff(key, field, va, vb))

    return SnapshotDiff(
        cycle_a=a.cycle,
        cycle_b=b.cycle,
        name_a=a.architecture_name,
        name_b=b.architecture_name,
        only_in_a=only_a,
        only_in_b=only_b,
        module_diffs=tuple(mod_diffs),
        connection_diffs=tuple(conn_diffs),
    )


def capture_state(arch: IArchitecture, cycle: int) -> StateSnapshot:
    """Snapshot the *current* live state of an elaborated architecture.

    Reads each module's ``snapshot_state()`` and each TLM connection's
    occupancy, freezing dict contents into tuples so the snapshot is a true
    immutable point-in-time value even if a module reuses its state dicts.
    """
    main_clock = arch.clocks[next(iter(arch.clocks))]

    modules: list[ModuleSnapshot] = []
    for mid, m in arch.modules.items():
        st = m.snapshot_state()
        fifo = tuple(sorted((k, int(v)) for k, v in st.internal_fifo_levels.items()))
        modules.append(
            ModuleSnapshot(
                module_id=mid,
                module_type=m.module_type(),
                busy=st.busy,
                current_op=st.current_op,
                internal_fifo_levels=fifo,
                last_stall_reason=st.last_stall_reason,
            )
        )

    connections: list[ConnectionSnapshot] = []
    for c in arch.connections:
        if not isinstance(c.runtime, TlmConnection):
            continue
        key = (
            f"{c.spec.source_module}.{c.spec.source_port}→"
            f"{c.spec.sink_module}.{c.spec.sink_port}"
        )
        connections.append(
            ConnectionSnapshot(
                key=key,
                in_flight=c.runtime.current_in_flight(),
                capacity=c.spec.fifo_depth,
                utilization=c.runtime.utilization(),
                tokens_dequeued=c.runtime.tokens_dequeued,
            )
        )

    return StateSnapshot(
        architecture_name=arch.name,
        cycle=cycle,
        time_ps=main_clock.current_time_ps(),
        modules=tuple(modules),
        connections=tuple(connections),
    )


def snapshot_at_cycle(
    arch: IArchitecture,
    at_cycle: int,
    max_cycles: int = 100_000,
) -> StateSnapshot:
    """Run the simulation deterministically and capture state at ``at_cycle``.

    This *is* the restore mechanism on this platform: because the runtime is
    deterministic, replaying from cycle 0 to N reconstructs exactly the state
    a binary checkpoint would have held at cycle N. If the simulation drains
    (quiesces) before ``at_cycle``, the last reached cycle is captured instead
    — the drained state is stable, so a later ``at_cycle`` sees the same thing.

    ``at_cycle`` is 0-based over post-tick cycle indices (matching the
    per-cycle hook / WaveformRecorder convention).
    """
    # Local import avoids a runner → snapshot import cycle at module load.
    from npu_sim.evaluation.runner import run_simulation

    captured: dict[str, StateSnapshot] = {}
    last_cycle = {"c": 0}

    def hook(cycle_index: int, live_arch: IArchitecture) -> None:
        last_cycle["c"] = cycle_index
        if cycle_index == at_cycle and "snap" not in captured:
            captured["snap"] = capture_state(live_arch, cycle_index)

    run_simulation(
        arch,
        max_cycles=max(at_cycle + 1, 1),
        per_cycle_hook=hook,
        # Keep spinning until the requested cycle even if the sim would
        # otherwise quiesce earlier — but the hook cap already bounds it.
        stop_at_quiescence=True,
    )

    if "snap" in captured:
        return captured["snap"]
    # Drained before at_cycle: capture the final (stable) state.
    return capture_state(arch, last_cycle["c"])
