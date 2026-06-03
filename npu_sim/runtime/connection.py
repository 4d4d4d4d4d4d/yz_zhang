"""TlmConnection: a concrete inter-module link with bounded FIFO + wire latency.

Reference: SPEC-002 §5 (and §5.1 for CDC, modeled here via separate spec types
but functionally identical at this phase — the additional sync_stages latency is
folded into latency_cycles at elaboration time when SystemC support lands).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Optional

from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.transport import ConnectionSpec, IConnection, TransportToken


@dataclass
class ProducerActivity:
    """Per-producer enqueue stats recorded by TlmConnection.

    SPEC-002 §3.4: used by BackpressureTracer to attribute multi-producer
    contention at a shared sink. `stall_ps_contributed` is the lower bound,
    approximated as `rejected * source_clock.period_ps` because each rejection
    consumes exactly one yield in the generator model.
    """

    producer_module: str
    accepted_count: int = 0
    rejected_count: int = 0
    stall_ps_contributed: int = 0

    @property
    def n_requests(self) -> int:
        return self.accepted_count + self.rejected_count


class TlmConnection(IConnection):
    """A FIFO-backed connection between two ports.

    Tokens enqueued at time T become visible to the sink at time T + latency,
    modelling wire delay (SPEC-002 §5 "physical line delay").
    """

    def __init__(self, spec: ConnectionSpec, source_clock: IClock) -> None:
        self._spec = spec
        self._source_clock = source_clock
        self._capacity = spec.fifo_depth
        # Each entry: (token, available_at_ps). Ordered by enqueue time.
        self._pending: deque[tuple[TransportToken, int]] = deque()
        # Lifetime counters (used by SimulationInvariantChecker per SPEC-002 §7).
        self._tokens_enqueued: int = 0
        self._tokens_dequeued: int = 0
        # ps timestamp of the most recent successful dequeue. Used by the
        # runner to compute SimulationResult.drain_time_ps — the meaningful
        # latency metric for steady-state pipelines (see SPEC-003 §7 finding
        # in docs/specs/README.md).
        self._last_dequeue_time_ps: int = 0
        # Peak in-flight reached during the run, for INV-7 verification.
        self._peak_in_flight: int = 0
        # Per-source attempt counters (SPEC-002 §3.4 multi-producer attribution).
        self._producer_activity: dict[str, ProducerActivity] = defaultdict(
            lambda: ProducerActivity(producer_module="")
        )

    def spec(self) -> ConnectionSpec:
        return self._spec

    def try_enqueue(self, token: TransportToken) -> bool:
        producer = token.source_module
        activity = self._producer_activity[producer]
        if activity.producer_module == "":
            # Lazy fill of producer_module on first sight (default factory uses "").
            activity.producer_module = producer

        if len(self._pending) >= self._capacity:
            activity.rejected_count += 1
            activity.stall_ps_contributed += self._source_clock.period_ps
            return False

        available_at = (
            self._source_clock.current_time_ps()
            + self._spec.latency_cycles * self._source_clock.period_ps
        )
        self._pending.append((token, available_at))
        self._tokens_enqueued += 1
        activity.accepted_count += 1
        if len(self._pending) > self._peak_in_flight:
            self._peak_in_flight = len(self._pending)
        return True

    def try_dequeue(self, now_ps: Optional[int] = None) -> Optional[TransportToken]:
        """Return the head token if its arrival time has been reached."""
        if not self._pending:
            return None
        now_ps = self._source_clock.current_time_ps() if now_ps is None else now_ps
        token, avail = self._pending[0]
        if avail > now_ps:
            return None
        self._pending.popleft()
        self._tokens_dequeued += 1
        self._last_dequeue_time_ps = now_ps
        return token

    def current_in_flight(self) -> int:
        return len(self._pending)

    def utilization(self) -> float:
        if self._capacity == 0:
            return 0.0
        return len(self._pending) / self._capacity

    @property
    def tokens_enqueued(self) -> int:
        return self._tokens_enqueued

    @property
    def tokens_dequeued(self) -> int:
        return self._tokens_dequeued

    @property
    def peak_in_flight(self) -> int:
        return self._peak_in_flight

    @property
    def last_dequeue_time_ps(self) -> int:
        """Timestamp of the most recent successful dequeue (0 if none)."""
        return self._last_dequeue_time_ps

    def producer_activity(self) -> list[ProducerActivity]:
        """Snapshot of per-producer attempt stats."""
        return [a for a in self._producer_activity.values() if a.producer_module]
