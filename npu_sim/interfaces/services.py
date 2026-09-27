"""Platform services injected via IModule.bind_services(): EventBus, StatSink.

Reference: SPEC-001 §3.1 bind_services(), SPEC-002 §4 stall reporting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class StallReason(Enum):
    """Stall categories. Reference: SPEC-002 §4.1."""

    INPUT_EMPTY = "input_empty"
    INPUT_PARTIAL = "input_partial"

    OUTPUT_FULL = "output_full"
    OUTPUT_BANDWIDTH = "output_bandwidth"

    INTERNAL_RESOURCE_CONFLICT = "internal_resource_conflict"
    INTERNAL_PIPELINE_HAZARD = "internal_pipeline_hazard"
    INTERNAL_CAPACITY = "internal_capacity"

    CAPABILITY_MISSING = "capability_missing"
    PRECISION_MISMATCH = "precision_mismatch"

    WAITING_FOR_COMMAND = "waiting_for_command"
    WAITING_FOR_SYNC = "waiting_for_sync"


@dataclass(frozen=True)
class StallEvent:
    """A single stall record. Reference: SPEC-002 §3.3."""

    time_ps: int
    module: str
    reason: StallReason
    duration_ps: int
    caused_by: Optional[str] = None
    details: dict = field(default_factory=dict)


class IEventBus(ABC):
    """Topic-based pub/sub used by platform components for cross-cutting events.

    BackpressureTracer in realtime mode subscribes to `stall.*` here.
    Reference: SPEC-002 §3.3.1.
    """

    @abstractmethod
    def publish(self, topic: str, payload: dict) -> None: ...

    @abstractmethod
    def subscribe(self, topic_pattern: str, handler: Callable[[dict], None]) -> None: ...


class IStatSink(ABC):
    """Sink for statistics including stall records.

    Reference: SPEC-002 §4.2, §3.5 (legality table).
    """

    @abstractmethod
    def record_stall(
        self,
        module: str,
        reason: StallReason,
        duration_ps: int,
        caused_by: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Record a stall. Implementations must enforce the legality table
        from SPEC-002 §3.5 and raise InvalidStallReport on violations.
        """

    @abstractmethod
    def record_counter(self, module: str, counter: str, value: int) -> None: ...

    @abstractmethod
    def load_stall_history(self) -> list[StallEvent]:
        """Return all recorded stall events. Used by BackpressureTracer in
        offline mode. Reference: SPEC-002 §3.3.1.
        """


# ============================================================
# Default in-memory implementations (for tests and Phase 1 use)
# ============================================================


class InMemoryEventBus(IEventBus):
    """Simple wildcard pub/sub backed by a dict.

    Topic patterns support trailing `.*` glob (e.g. "stall.*" matches
    "stall.output_full"). No other wildcards are supported.
    """

    def __init__(self) -> None:
        self._subscribers: list[tuple[str, Callable[[dict], None]]] = []

    def publish(self, topic: str, payload: dict) -> None:
        for pattern, handler in self._subscribers:
            if self._match(pattern, topic):
                handler(payload)

    def subscribe(self, topic_pattern: str, handler: Callable[[dict], None]) -> None:
        self._subscribers.append((topic_pattern, handler))

    @staticmethod
    def _match(pattern: str, topic: str) -> bool:
        if pattern == topic:
            return True
        if pattern.endswith(".*"):
            return topic.startswith(pattern[:-1])
        return False


class InMemoryStatSink(IStatSink):
    """In-memory stat sink that enforces SPEC-002 §3.5 legality on record_stall.

    Publishes "stall.<reason>" to an optional EventBus on every accepted record,
    enabling realtime tracer mode.
    """

    # Reasons that mandate non-null caused_by (SPEC-002 §3.5)
    _MUST_HAVE_CAUSED_BY: frozenset[StallReason] = frozenset({
        StallReason.OUTPUT_FULL,
        StallReason.OUTPUT_BANDWIDTH,
        StallReason.WAITING_FOR_COMMAND,
        StallReason.WAITING_FOR_SYNC,
    })

    # Reasons that mandate null caused_by
    _MUST_BE_NULL_CAUSED_BY: frozenset[StallReason] = frozenset({
        StallReason.INTERNAL_RESOURCE_CONFLICT,
        StallReason.INTERNAL_PIPELINE_HAZARD,
        StallReason.INTERNAL_CAPACITY,
    })

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._stalls: list[StallEvent] = []
        self._counters: dict[tuple[str, str], int] = {}
        self._event_bus = event_bus
        self._now_ps_fn: Callable[[], int] = lambda: 0  # overwritten when clock bound

    def bind_clock_fn(self, now_ps_fn: Callable[[], int]) -> None:
        """Phase 1 helper: lets the sink stamp events with simulated time."""
        self._now_ps_fn = now_ps_fn

    def record_stall(
        self,
        module: str,
        reason: StallReason,
        duration_ps: int,
        caused_by: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        from npu_sim.core.errors import InvalidStallReport, MapperBugError

        # SPEC-002 §3.5 legality enforcement
        if reason == StallReason.CAPABILITY_MISSING:
            raise MapperBugError(
                f"CAPABILITY_MISSING stall at {module}: this indicates a Mapper bug "
                f"(an op was routed to a module that cannot execute it)."
            )
        if reason in self._MUST_HAVE_CAUSED_BY and caused_by is None:
            raise InvalidStallReport(
                f"Stall reason {reason.value} requires caused_by; got None at {module}."
            )
        if reason in self._MUST_BE_NULL_CAUSED_BY and caused_by is not None:
            raise InvalidStallReport(
                f"Stall reason {reason.value} forbids caused_by; got {caused_by!r} at {module}."
            )

        event = StallEvent(
            time_ps=self._now_ps_fn(),
            module=module,
            reason=reason,
            duration_ps=duration_ps,
            caused_by=caused_by,
            details=details or {},
        )
        self._stalls.append(event)

        if self._event_bus is not None:
            self._event_bus.publish(
                f"stall.{reason.value}",
                {
                    "time_ps": event.time_ps,
                    "module": event.module,
                    "reason": event.reason,
                    "duration_ps": event.duration_ps,
                    "caused_by": event.caused_by,
                    "details": event.details,
                },
            )

    def record_counter(self, module: str, counter: str, value: int) -> None:
        key = (module, counter)
        self._counters[key] = self._counters.get(key, 0) + value

    def load_stall_history(self) -> list[StallEvent]:
        return list(self._stalls)

    def get_counter(self, module: str, counter: str) -> int:
        return self._counters.get((module, counter), 0)
