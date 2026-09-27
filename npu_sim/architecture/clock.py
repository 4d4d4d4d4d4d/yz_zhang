"""Minimal IClock implementation used by the Phase 1/3 Python-only path.

This is a placeholder until the SystemC kernel is wired in (Phase 0 design).
It does not actually advance time on wait_*() — those are no-ops — but it
exposes the right interface for bind_services() and for tests that only
need the static metadata (domain_id, period_ps).
"""

from __future__ import annotations

from npu_sim.interfaces.clock import IClock, IClockEvent


class SimpleClock(IClock):

    def __init__(self, domain_id: str, period_ps: int) -> None:
        self._domain_id = domain_id
        self._period_ps = int(period_ps)
        self._now_ps = 0

    @property
    def domain_id(self) -> str:
        return self._domain_id

    @property
    def period_ps(self) -> int:
        return self._period_ps

    def current_time_ps(self) -> int:
        return self._now_ps

    def current_cycle(self) -> int:
        return self._now_ps // self._period_ps if self._period_ps else 0

    def wait_cycles(self, n: int) -> None:
        # No-op in the Python-only path. SystemC integration will replace this.
        self._now_ps += n * self._period_ps

    def wait_until_ps(self, target_time_ps: int) -> None:
        if target_time_ps < self._now_ps:
            raise ValueError(
                f"wait_until_ps({target_time_ps}) is in the past "
                f"(now={self._now_ps})."
            )
        self._now_ps = target_time_ps

    def wait_event(self, event: IClockEvent) -> None:
        # No-op placeholder.
        pass

    def is_same_domain(self, other: IClock) -> bool:
        return (
            self.domain_id == other.domain_id
            and self.period_ps == other.period_ps
        )
