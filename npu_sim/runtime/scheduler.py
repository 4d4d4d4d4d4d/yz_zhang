"""Minimal cooperative scheduler driving generator-based module behaviors.

Reference: SPEC-002 §3.2 (blocking send is implemented via yield) and ADR-001.1
(SystemC kernel is the target; this Python scheduler is the Phase 1/2 stand-in).

One scheduler step:
  1. Advance every live behavior by one `next()` call.
  2. Increment the clock by one period.
  3. Repeat until either all behaviors finish or max_cycles is exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator, Optional

from npu_sim.architecture.clock import SimpleClock


@dataclass
class _Process:
    behavior: Iterator
    module_id: str = "<anon>"


@dataclass
class SchedulerResult:
    cycles_run: int
    finished: int
    deadlocked: int                 # behaviors still alive at max_cycles
    behavior_ids_alive: list[str] = field(default_factory=list)


class SimpleScheduler:
    """Round-robin cycle-stepped scheduler for generator-based behaviors."""

    def __init__(self, clock: SimpleClock) -> None:
        self._clock = clock
        self._processes: list[_Process] = []

    def spawn(self, behavior: Iterator, module_id: Optional[str] = None) -> None:
        """Register a generator behavior. The first step is taken on next run()."""
        self._processes.append(_Process(behavior=behavior, module_id=module_id or "<anon>"))

    def spawn_many(self, pairs: Iterable[tuple[Iterator, str]]) -> None:
        for behavior, mid in pairs:
            self.spawn(behavior, mid)

    def alive_ids(self) -> list[str]:
        """Module ids whose behavior generator is still running."""
        return [p.module_id for p in self._processes]

    def run(
        self,
        max_cycles: int = 10_000,
        activity_probe: Optional[Callable[[], bool]] = None,
    ) -> SchedulerResult:
        """Advance the simulation up to max_cycles.

        ``activity_probe`` (optional): a side-effect-free predicate checked
        after each fully-stepped cycle. When it returns False the simulation
        has quiesced (nothing busy, nothing in flight, no live source), so
        remaining cycles would only spin idle pollers — the loop breaks
        early. All recorded metrics are already final at quiescence, so the
        result is bit-identical to running to max_cycles. Default None ⇒
        legacy behavior (run to max_cycles / all-finished).
        """
        cycle = 0
        finished = 0
        while cycle < max_cycles and self._processes:
            still_running: list[_Process] = []
            for p in self._processes:
                try:
                    next(p.behavior)
                    still_running.append(p)
                except StopIteration:
                    finished += 1
            self._processes = still_running
            if not self._processes:
                break
            self._clock.wait_cycles(1)
            cycle += 1
            if activity_probe is not None and not activity_probe():
                break
        return SchedulerResult(
            cycles_run=cycle,
            finished=finished,
            deadlocked=len(self._processes),
            behavior_ids_alive=[p.module_id for p in self._processes],
        )
