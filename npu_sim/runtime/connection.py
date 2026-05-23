"""TlmConnection: a concrete inter-module link with bounded FIFO + wire latency.

Reference: SPEC-002 §5 (and §5.1 for CDC, modeled here via separate spec types
but functionally identical at this phase — the additional sync_stages latency is
folded into latency_cycles at elaboration time when SystemC support lands).
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.transport import ConnectionSpec, IConnection, TransportToken


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

    def spec(self) -> ConnectionSpec:
        return self._spec

    def try_enqueue(self, token: TransportToken) -> bool:
        if len(self._pending) >= self._capacity:
            return False
        available_at = (
            self._source_clock.current_time_ps()
            + self._spec.latency_cycles * self._source_clock.period_ps
        )
        self._pending.append((token, available_at))
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
        return token

    def current_in_flight(self) -> int:
        return len(self._pending)

    def utilization(self) -> float:
        if self._capacity == 0:
            return 0.0
        return len(self._pending) / self._capacity
