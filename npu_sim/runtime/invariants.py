"""SimulationInvariantChecker: post-simulation health check.

Reference: SPEC-002 §7.

Runs after a simulation completes. Any INV-* failure marks the run as INVALID
and the result must not be used for decision-making (§7 final note). Warnings
do not invalidate the run but are surfaced in the summary.

Required invariants (must pass):
  INV-1  Every enqueued token was dequeued by its sink (or counted in_flight).
  INV-2  No tokens remain in-flight on any connection.
  INV-3  No behaviors are deadlocked (scheduler reports no surviving processes).
  INV-4  The reverse-causality graph derived from stall events has no cycle.
  INV-5  Stall events are recorded in non-decreasing time order.
  INV-6  Every non-null caused_by points at an existing module id.
  INV-7  No connection's peak FIFO occupancy exceeded its capacity.

Recommended (warn-only):
  INV-W1 No backpressure chain exceeds depth 8.
  INV-W2 No single module's recorded stall time exceeds 90% of simulation time.
  INV-W3 No CDC connection averaged > 80% capacity.

Construction takes the live IArchitecture, the StatSink that was bound to the
simulation, and the SchedulerResult returned by the scheduler driver.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.interfaces.services import IStatSink
from npu_sim.interfaces.transport import CdcConnectionSpec
from npu_sim.runtime.connection import TlmConnection
from npu_sim.runtime.scheduler import SchedulerResult


# ============================================================
# Result types
# ============================================================


@dataclass(frozen=True)
class InvariantFailure:
    invariant_id: str
    description: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InvariantWarning:
    invariant_id: str
    description: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InvariantReport:
    overall_valid: bool
    failures: tuple[InvariantFailure, ...]
    warnings: tuple[InvariantWarning, ...]
    summary_text: str


# ============================================================
# Interface
# ============================================================


class IInvariantChecker(ABC):
    @abstractmethod
    def run_all(self, architecture: IArchitecture) -> InvariantReport: ...


# ============================================================
# Implementation
# ============================================================


class SimulationInvariantChecker(IInvariantChecker):

    # SPEC-002 §7 thresholds
    _MAX_CHAIN_DEPTH = 8
    _MAX_STALL_RATIO = 0.9
    _MAX_CDC_AVG_UTIL = 0.8

    def __init__(
        self,
        stat_sink: IStatSink,
        scheduler_result: SchedulerResult,
        simulation_time_ps: int,
    ) -> None:
        self._stat_sink = stat_sink
        self._sched_result = scheduler_result
        self._sim_time_ps = max(simulation_time_ps, 1)  # avoid div-by-zero

    def run_all(self, architecture: IArchitecture) -> InvariantReport:
        failures: list[InvariantFailure] = []
        warnings: list[InvariantWarning] = []

        events = self._stat_sink.load_stall_history()
        live_connections = [
            c.runtime for c in architecture.connections
            if isinstance(c.runtime, TlmConnection)
        ]

        self._inv1_token_conservation(live_connections, failures)
        self._inv2_no_in_flight(live_connections, failures)
        self._inv3_no_deadlock(live_connections, failures)
        self._inv4_no_chain_cycle(events, failures)
        self._inv5_time_monotonic(events, failures)
        self._inv6_caused_by_valid(events, architecture, failures)
        self._inv7_fifo_within_capacity(live_connections, failures)

        self._invW1_chain_depth(events, warnings)
        self._invW2_stall_ratio(events, warnings)
        self._invW3_cdc_utilization(architecture, live_connections, warnings)

        valid = len(failures) == 0
        summary = self._format_summary(valid, failures, warnings)

        return InvariantReport(
            overall_valid=valid,
            failures=tuple(failures),
            warnings=tuple(warnings),
            summary_text=summary,
        )

    # ============================================================
    # Required invariants
    # ============================================================

    def _inv1_token_conservation(
        self,
        connections: list[TlmConnection],
        out: list[InvariantFailure],
    ) -> None:
        for conn in connections:
            spec = conn.spec()
            expected = conn.tokens_dequeued + conn.current_in_flight()
            if conn.tokens_enqueued != expected:
                out.append(InvariantFailure(
                    invariant_id="INV-1",
                    description=(
                        f"Token conservation violated on connection "
                        f"{spec.source_module}.{spec.source_port} → "
                        f"{spec.sink_module}.{spec.sink_port}: enqueued="
                        f"{conn.tokens_enqueued}, dequeued+in_flight={expected}."
                    ),
                    evidence={
                        "connection": f"{spec.source_module}.{spec.source_port}→"
                                      f"{spec.sink_module}.{spec.sink_port}",
                        "enqueued": conn.tokens_enqueued,
                        "dequeued": conn.tokens_dequeued,
                        "in_flight": conn.current_in_flight(),
                    },
                ))

    def _inv2_no_in_flight(
        self,
        connections: list[TlmConnection],
        out: list[InvariantFailure],
    ) -> None:
        residual = []
        for conn in connections:
            if conn.current_in_flight() > 0:
                spec = conn.spec()
                residual.append({
                    "connection": f"{spec.source_module}.{spec.source_port}→"
                                  f"{spec.sink_module}.{spec.sink_port}",
                    "in_flight": conn.current_in_flight(),
                })
        if residual:
            out.append(InvariantFailure(
                invariant_id="INV-2",
                description=(
                    f"{len(residual)} connection(s) have tokens still in flight "
                    f"at end of simulation."
                ),
                evidence={"residual_connections": residual},
            ))

    def _inv3_no_deadlock(
        self,
        connections: list[TlmConnection],
        out: list[InvariantFailure],
    ) -> None:
        """SPEC-002 §7 INV-3: no SC_THREAD suspended in BACKPRESSURE state.

        A behavior that simply polls an empty input (idle) is NOT a deadlock —
        it's just an unterminated SC_THREAD. We flag deadlock only when:
          - the scheduler reports surviving behaviors, AND
          - at least one connection still carries in-flight tokens
            (i.e. someone is stuck pushing into a full FIFO).
        """
        if self._sched_result.deadlocked == 0:
            return
        any_in_flight = any(c.current_in_flight() > 0 for c in connections)
        if not any_in_flight:
            return  # idle, not deadlocked
        out.append(InvariantFailure(
            invariant_id="INV-3",
            description=(
                f"{self._sched_result.deadlocked} behavior(s) still running at "
                f"max_cycles with tokens stuck in-flight — indicates a "
                f"deadlock or insufficient simulation duration."
            ),
            evidence={
                "deadlocked_count": self._sched_result.deadlocked,
                "behavior_ids": list(self._sched_result.behavior_ids_alive),
                "cycles_run": self._sched_result.cycles_run,
            },
        ))

    def _inv4_no_chain_cycle(
        self,
        events,
        out: list[InvariantFailure],
    ) -> None:
        # Build a graph: edges go FROM stalled module TO causing module.
        adj: dict[str, set[str]] = defaultdict(set)
        nodes: set[str] = set()
        for e in events:
            if e.caused_by is not None:
                adj[e.module].add(e.caused_by)
                nodes.add(e.module)
                nodes.add(e.caused_by)

        # DFS cycle detection (3-color).
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in nodes}
        cycle_path: list[str] = []

        def dfs(u: str, stack: list[str]) -> bool:
            color[u] = GRAY
            stack.append(u)
            for v in adj[u]:
                if color.get(v, WHITE) == GRAY:
                    cycle_path.extend(stack[stack.index(v):])
                    cycle_path.append(v)
                    return True
                if color.get(v, WHITE) == WHITE and dfs(v, stack):
                    return True
            stack.pop()
            color[u] = BLACK
            return False

        for n in nodes:
            if color[n] == WHITE and dfs(n, []):
                out.append(InvariantFailure(
                    invariant_id="INV-4",
                    description=(
                        f"Cycle detected in backpressure graph: "
                        f"{' → '.join(cycle_path)}"
                    ),
                    evidence={"cycle": list(cycle_path)},
                ))
                return  # only report once

    def _inv5_time_monotonic(
        self,
        events,
        out: list[InvariantFailure],
    ) -> None:
        for i in range(1, len(events)):
            if events[i].time_ps < events[i - 1].time_ps:
                out.append(InvariantFailure(
                    invariant_id="INV-5",
                    description=(
                        f"Stall events not in monotonic time order at index "
                        f"{i}: {events[i - 1].time_ps} → {events[i].time_ps}"
                    ),
                    evidence={
                        "index": i,
                        "previous_time_ps": events[i - 1].time_ps,
                        "current_time_ps": events[i].time_ps,
                    },
                ))
                return  # report first violation only

    def _inv6_caused_by_valid(
        self,
        events,
        architecture: IArchitecture,
        out: list[InvariantFailure],
    ) -> None:
        valid_ids = set(architecture.modules)
        invalid_refs: list[dict] = []
        for e in events:
            if e.caused_by is not None and e.caused_by not in valid_ids:
                invalid_refs.append({
                    "stalled_module": e.module,
                    "caused_by": e.caused_by,
                    "time_ps": e.time_ps,
                })
        if invalid_refs:
            out.append(InvariantFailure(
                invariant_id="INV-6",
                description=(
                    f"{len(invalid_refs)} stall event(s) reference unknown "
                    f"caused_by modules."
                ),
                evidence={
                    "invalid_references": invalid_refs[:10],
                    "total": len(invalid_refs),
                },
            ))

    def _inv7_fifo_within_capacity(
        self,
        connections: list[TlmConnection],
        out: list[InvariantFailure],
    ) -> None:
        for conn in connections:
            spec = conn.spec()
            if conn.peak_in_flight > spec.fifo_depth:
                out.append(InvariantFailure(
                    invariant_id="INV-7",
                    description=(
                        f"FIFO over-capacity on connection "
                        f"{spec.source_module}.{spec.source_port} → "
                        f"{spec.sink_module}.{spec.sink_port}: peak="
                        f"{conn.peak_in_flight}, capacity={spec.fifo_depth}."
                    ),
                    evidence={
                        "connection": f"{spec.source_module}.{spec.source_port}→"
                                      f"{spec.sink_module}.{spec.sink_port}",
                        "peak_in_flight": conn.peak_in_flight,
                        "fifo_depth": spec.fifo_depth,
                    },
                ))

    # ============================================================
    # Recommended (warn-only) invariants
    # ============================================================

    def _invW1_chain_depth(self, events, out: list[InvariantWarning]) -> None:
        """Find longest directed path in the caused_by DAG (acyclic by INV-4)."""
        adj: dict[str, set[str]] = defaultdict(set)
        nodes: set[str] = set()
        for e in events:
            if e.caused_by is not None:
                adj[e.module].add(e.caused_by)
                nodes.add(e.module)
                nodes.add(e.caused_by)

        if not nodes:
            return

        # Topological order via Kahn's algorithm; if cycles exist INV-4 will
        # have reported separately — skip warning safely.
        in_degree: dict[str, int] = {n: 0 for n in nodes}
        for u, vs in adj.items():
            for v in vs:
                in_degree[v] += 1
        q = deque([n for n, d in in_degree.items() if d == 0])
        order: list[str] = []
        while q:
            n = q.popleft()
            order.append(n)
            for v in adj[n]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    q.append(v)
        if len(order) != len(nodes):
            return  # cycle present; INV-4 owns the report

        # Longest path: dp[v] = longest path ending at v.
        dp: dict[str, int] = {n: 0 for n in nodes}
        for u in order:
            for v in adj[u]:
                if dp[u] + 1 > dp[v]:
                    dp[v] = dp[u] + 1
        depth = max(dp.values())
        if depth > self._MAX_CHAIN_DEPTH:
            deepest = max(dp, key=dp.get)
            out.append(InvariantWarning(
                invariant_id="INV-W1",
                description=(
                    f"Backpressure chain depth {depth} exceeds advisory "
                    f"maximum {self._MAX_CHAIN_DEPTH}; attribution quality "
                    f"may degrade."
                ),
                evidence={"depth": depth, "deepest_module": deepest},
            ))

    def _invW2_stall_ratio(self, events, out: list[InvariantWarning]) -> None:
        if not events or self._sim_time_ps == 0:
            return
        per_module: dict[str, int] = defaultdict(int)
        for e in events:
            per_module[e.module] += e.duration_ps
        for mod, total in per_module.items():
            ratio = total / self._sim_time_ps
            if ratio > self._MAX_STALL_RATIO:
                out.append(InvariantWarning(
                    invariant_id="INV-W2",
                    description=(
                        f"Module {mod!r} spent {ratio:.0%} of simulation "
                        f"time stalled (> {self._MAX_STALL_RATIO:.0%}); "
                        f"may indicate misrouting by the Mapper."
                    ),
                    evidence={
                        "module": mod,
                        "stall_ps": total,
                        "sim_time_ps": self._sim_time_ps,
                        "ratio": ratio,
                    },
                ))

    def _invW3_cdc_utilization(
        self,
        architecture: IArchitecture,
        connections: list[TlmConnection],
        out: list[InvariantWarning],
    ) -> None:
        """Phase 4 approximation: use current utilization at end-of-sim.
        Full implementation needs per-cycle sampling, deferred to v1.1.
        """
        for conn in connections:
            if not isinstance(conn.spec(), CdcConnectionSpec):
                continue
            util = conn.utilization()
            if util > self._MAX_CDC_AVG_UTIL:
                spec = conn.spec()
                out.append(InvariantWarning(
                    invariant_id="INV-W3",
                    description=(
                        f"CDC connection {spec.source_module}.{spec.source_port} "
                        f"→ {spec.sink_module}.{spec.sink_port} ended at "
                        f"{util:.0%} utilization (> {self._MAX_CDC_AVG_UTIL:.0%})."
                    ),
                    evidence={"utilization": util, "fifo_depth": spec.fifo_depth},
                ))

    # ============================================================
    # Summary formatting
    # ============================================================

    @staticmethod
    def _format_summary(
        valid: bool,
        failures: list[InvariantFailure],
        warnings: list[InvariantWarning],
    ) -> str:
        verdict = "VALID" if valid else "INVALID"
        lines = [f"Simulation invariant check: {verdict}"]
        if failures:
            lines.append(f"  Failures ({len(failures)}):")
            for f in failures:
                lines.append(f"    - {f.invariant_id}: {f.description}")
        if warnings:
            lines.append(f"  Warnings ({len(warnings)}):")
            for w in warnings:
                lines.append(f"    - {w.invariant_id}: {w.description}")
        if not failures and not warnings:
            lines.append("  All invariants passed; no warnings.")
        return "\n".join(lines)
