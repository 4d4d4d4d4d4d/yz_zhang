"""BackpressureTracer: stall-event consumer that builds reverse-causality DAGs.

Reference: SPEC-002 §3.3 (StallChain construction) and §3.4 (multi-producer
attribution).

Two operating modes are supported (SPEC-002 §3.3.1):

  Realtime — constructed with an `IEventBus`; subscribes to `stall.*` and
             builds its event history incrementally as the simulation runs.

  Offline  — constructed with an `IStatSink`; reads `load_stall_history()`
             once and operates on the snapshot.

After the simulation, callers query `trace_chain(end_module, time_window)`
to walk the `caused_by` graph backwards from the given module and obtain
the contributing root causes plus the bottleneck.

`trace_multi_producer_contention(sink_module, ...)` is declared per §3.4
but only returns events backed by per-producer attribution data, which is
not yet recorded by the Phase 2 connection layer. The method exists so the
report API is stable; full attribution lands when TlmConnection records
contention details.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union

from npu_sim.interfaces.services import (
    IEventBus,
    IStatSink,
    StallEvent,
    StallReason,
)


# ============================================================
# Data classes
# ============================================================


class TracerMode(Enum):
    REALTIME = "realtime"
    OFFLINE = "offline"


@dataclass(frozen=True)
class ChainLink:
    """One edge in the reverse causality DAG."""

    from_module: str
    to_module: Optional[str]            # None => internal stall (root)
    contribution_ps: int
    reasons: tuple[StallReason, ...] = ()


@dataclass(frozen=True)
class StallCause:
    """A leaf cause: a module whose internal stalls drove the chain.

    For implicit root causes (modules that did NOT record any stall but were
    the deepest `caused_by` target), `reason` is None and the contribution is
    the sum of inbound link contributions.
    """

    module: str
    reason: Optional[StallReason]
    contribution_ps: int
    percentage: float
    is_implicit: bool = False


@dataclass(frozen=True)
class StallChain:
    """Output of trace_chain. A DAG rooted at `end_module`."""

    end_module: str
    root_causes: tuple[StallCause, ...]
    chain_links: tuple[ChainLink, ...]
    total_stall_time_ps: int
    bottleneck_module: str

    def involves_module(self, module_id: str) -> bool:
        if module_id == self.bottleneck_module or module_id == self.end_module:
            return True
        if any(c.module == module_id for c in self.root_causes):
            return True
        for link in self.chain_links:
            if link.from_module == module_id or link.to_module == module_id:
                return True
        return False


@dataclass
class ProducerActivity:
    """Per-producer activity at a contended sink. SPEC-002 §3.4."""

    producer_module: str
    n_requests: int
    accepted_count: int
    rejected_count: int
    stall_ps_contributed: int


@dataclass
class MultiProducerContention:
    """Sink-side multi-producer contention record. SPEC-002 §3.4."""

    sink_module: str
    time_window_ps: tuple[int, int]
    producers: list[ProducerActivity] = field(default_factory=list)
    bottleneck_resource: str = ""
    total_contention_ps: int = 0


# ============================================================
# Tracer
# ============================================================


class BackpressureTracer:

    def __init__(
        self,
        mode: TracerMode,
        source: Union[IEventBus, IStatSink],
    ) -> None:
        self._mode = mode
        self._events: list[StallEvent] = []

        if mode == TracerMode.REALTIME:
            if not isinstance(source, IEventBus):
                raise TypeError(
                    f"REALTIME tracer requires IEventBus; got {type(source).__name__}."
                )
            source.subscribe("stall.*", self._on_event)
        elif mode == TracerMode.OFFLINE:
            if not isinstance(source, IStatSink):
                raise TypeError(
                    f"OFFLINE tracer requires IStatSink; got {type(source).__name__}."
                )
            self._events = list(source.load_stall_history())
        else:
            raise ValueError(f"Unknown tracer mode: {mode!r}")

    # --- realtime ingest ---

    def _on_event(self, payload: dict) -> None:
        self._events.append(
            StallEvent(
                time_ps=payload.get("time_ps", 0),
                module=payload["module"],
                reason=payload["reason"],
                duration_ps=payload["duration_ps"],
                caused_by=payload.get("caused_by"),
                details=payload.get("details", {}),
            )
        )

    # --- queries ---

    @property
    def events(self) -> list[StallEvent]:
        """Snapshot of events seen so far."""
        return list(self._events)

    def trace_chain(
        self,
        end_module: str,
        time_window_ps: Optional[tuple[int, int]] = None,
    ) -> StallChain:
        """Walk the caused_by DAG backwards from `end_module`.

        Algorithm (SPEC-002 §3.3):
          1. Restrict events to those in `time_window_ps`.
          2. BFS over modules starting at `end_module`, following the
             `caused_by` field on every event.
          3. Record one ChainLink per event traversed; treat events with
             caused_by=None as internal (explicit) root causes.
          4. A module reached as a `caused_by` target but with no events of
             its own is an implicit root (the source of backpressure that
             didn't itself stall — e.g. a slow consumer).
          5. Bottleneck = root cause with the largest aggregate contribution.
        """

        events_in_window = self._filter(time_window_ps)

        # Index by stalled module for quick lookup.
        by_module: dict[str, list[StallEvent]] = defaultdict(list)
        for e in events_in_window:
            by_module[e.module].append(e)

        visited: set[str] = set()
        queue: deque[str] = deque([end_module])
        links: list[ChainLink] = []
        explicit_roots: list[StallCause] = []
        implicit_root_inbound: dict[str, int] = defaultdict(int)
        total_stall = 0

        while queue:
            m = queue.popleft()
            if m in visited:
                continue
            visited.add(m)

            module_events = by_module.get(m, [])
            for e in module_events:
                total_stall += e.duration_ps
                if e.caused_by is None:
                    # Internal stall — m is an explicit root cause.
                    explicit_roots.append(
                        StallCause(
                            module=m,
                            reason=e.reason,
                            contribution_ps=e.duration_ps,
                            percentage=0.0,  # filled in below
                        )
                    )
                else:
                    links.append(
                        ChainLink(
                            from_module=m,
                            to_module=e.caused_by,
                            contribution_ps=e.duration_ps,
                            reasons=(e.reason,),
                        )
                    )
                    if e.caused_by not in visited:
                        queue.append(e.caused_by)

        # Any module that was targeted by a link but did NOT itself record
        # stall events is an "implicit" root cause.
        link_targets = {l.to_module for l in links if l.to_module is not None}
        for tgt in link_targets:
            if tgt not in by_module:
                # Sum inbound contributions toward this implicit root.
                for l in links:
                    if l.to_module == tgt:
                        implicit_root_inbound[tgt] += l.contribution_ps

        # Aggregate explicit roots by (module, reason) so a module that stalled
        # internally many times shows up as one entry.
        explicit_agg: dict[tuple[str, StallReason], int] = defaultdict(int)
        for r in explicit_roots:
            explicit_agg[(r.module, r.reason)] += r.contribution_ps

        all_root_total = (
            sum(explicit_agg.values()) + sum(implicit_root_inbound.values())
        )

        final_roots: list[StallCause] = []
        for (mod, reason), contrib in explicit_agg.items():
            pct = (contrib / all_root_total) if all_root_total else 0.0
            final_roots.append(
                StallCause(
                    module=mod, reason=reason, contribution_ps=contrib,
                    percentage=pct, is_implicit=False,
                )
            )
        for tgt, contrib in implicit_root_inbound.items():
            pct = (contrib / all_root_total) if all_root_total else 0.0
            final_roots.append(
                StallCause(
                    module=tgt, reason=None, contribution_ps=contrib,
                    percentage=pct, is_implicit=True,
                )
            )

        if final_roots:
            bottleneck = max(final_roots, key=lambda rc: rc.contribution_ps).module
        else:
            bottleneck = end_module

        # Sort outputs deterministically for testability.
        final_roots.sort(
            key=lambda rc: (-rc.contribution_ps, rc.module, str(rc.reason))
        )
        links.sort(
            key=lambda l: (l.from_module, l.to_module or "", -l.contribution_ps)
        )

        return StallChain(
            end_module=end_module,
            root_causes=tuple(final_roots),
            chain_links=tuple(links),
            total_stall_time_ps=total_stall,
            bottleneck_module=bottleneck,
        )

    def trace_multi_producer_contention(
        self,
        sink_module: str,
        time_window_ps: Optional[tuple[int, int]] = None,
    ) -> list[MultiProducerContention]:
        """SPEC-002 §3.4 — multi-producer contention at a shared sink.

        Phase 4 status: API is stable but returns an empty list until the
        connection layer records per-producer attempts. Adding that
        bookkeeping is a small follow-up (TlmConnection.try_enqueue annotated
        with the calling producer id) and is tracked separately.
        """
        del sink_module, time_window_ps  # noqa: F841 (API signature reserved)
        return []

    # --- helpers ---

    def _filter(
        self,
        window: Optional[tuple[int, int]],
    ) -> list[StallEvent]:
        if window is None:
            return list(self._events)
        lo, hi = window
        return [e for e in self._events if lo <= e.time_ps <= hi]
