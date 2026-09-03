"""Use Case evaluation driver: elaborate → simulate → invariant-check → analyze.

Reference: SPEC-003 §7 R7 (the "AGU-W bandwidth half" archetype).

The runner is intentionally module-agnostic: it works for any IArchitecture
whose modules expose a `behavior()` generator (the Phase 1/2 Python-side
convention pending SystemC integration).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.architecture.clock import SimpleClock
from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.interfaces.services import (
    InMemoryEventBus,
    InMemoryStatSink,
    StallEvent,
)
from npu_sim.runtime.connection import TlmConnection
from npu_sim.runtime.invariants import (
    InvariantReport,
    SimulationInvariantChecker,
)
from npu_sim.runtime.scheduler import SchedulerResult, SimpleScheduler
from npu_sim.runtime.tracer import BackpressureTracer, TracerMode


@dataclass(frozen=True)
class SimulationResult:
    """The result of running one architecture through the Phase 1/2 driver.

    Combines scheduler liveness, invariant verdict, bottleneck identification,
    and aggregate area/power so two runs can be compared without re-reading
    the architecture.
    """

    architecture_name: str
    cycles_run: int
    sim_time_ps: int
    drain_time_ps: int                     # max last-dequeue ps across all connections
    scheduler_result: SchedulerResult
    invariant_report: InvariantReport
    stall_events: tuple[StallEvent, ...]
    bottleneck_module: Optional[str]
    total_stall_ps: int
    per_module_stall_ps: dict[str, int]
    tokens_delivered: dict[str, int]              # connection key → dequeued
    tokens_in_flight: dict[str, int]
    total_area_um2: float
    total_static_power_uw: float
    elaboration_warnings: tuple[str, ...]


def run_simulation(
    arch: IArchitecture,
    max_cycles: int = 10_000,
    per_cycle_hook: Optional[Callable[[int, IArchitecture], None]] = None,
    stop_at_quiescence: bool = True,
) -> SimulationResult:
    """Drive every behavior()-bearing module and produce a SimulationResult.

    The architecture must have been elaborated by :class:`ArchitectureElaborator`
    so that the StatSink behind its modules is the one we can later inspect.
    The Elaborator is the canonical source for the bound services; we fetch
    the sink and bus from the first module's port owner record so this
    runner does not require them to be threaded through separately.

    ``per_cycle_hook(cycle_index, arch)`` is invoked AFTER each scheduled
    tick advances; pass :class:`npu_sim.reporting.waveform.WaveformRecorder`
    to capture cycle-by-cycle state for waveform rendering.

    ``stop_at_quiescence`` (default True): break the scheduler early once the
    simulation has provably drained — no module busy, no token in any
    connection FIFO, and no live source generator that could emit more. All
    metrics are final at that point, so results are bit-identical to running
    to ``max_cycles``, but post-drain idle spinning (often the large majority
    of cycles) is skipped. Set False to force running to ``max_cycles``.
    """

    main_clock: SimpleClock = arch.clocks[next(iter(arch.clocks))]

    # Pull the StatSink that the Elaborator bound to every module. All
    # modules in an architecture share the same sink instance, so reading
    # from any module's stat_sink works. We look at the first module that
    # exposes the attribute.
    stat_sink = _extract_stat_sink(arch)
    stat_sink.bind_clock_fn(main_clock.current_time_ps)

    # Spawn behaviors.
    scheduler = SimpleScheduler(main_clock)
    for mid, module in arch.modules.items():
        if hasattr(module, "behavior"):
            scheduler.spawn(module.behavior(), module_id=mid)

    probe = _make_quiescence_probe(arch, scheduler) if stop_at_quiescence else None

    if per_cycle_hook is None:
        sched_result = scheduler.run(max_cycles=max_cycles, activity_probe=probe)
    else:
        # Tick the scheduler one cycle at a time so we can sample state.
        # SimpleScheduler.run() advances *by* its max_cycles argument (not
        # *to* it), so passing 1 each iteration gives a clean 1-cycle step.
        # Slightly slower than batched run() but only used when a recorder
        # is attached.
        sched_result = None
        cumulative = SchedulerResult(cycles_run=0, finished=0, deadlocked=0, behavior_ids_alive=[])
        for c in range(max_cycles):
            step = scheduler.run(max_cycles=1)
            cumulative = SchedulerResult(
                cycles_run=cumulative.cycles_run + step.cycles_run,
                finished=cumulative.finished + step.finished,
                deadlocked=step.deadlocked,
                behavior_ids_alive=step.behavior_ids_alive,
            )
            per_cycle_hook(c, arch)
            if step.cycles_run == 0:  # scheduler exhausted (all behaviors done)
                break
            if probe is not None and not probe():
                # Quiesced: sim has provably drained, so all recorded state is
                # final. Stop sampling post-drain idle cycles (bit-identical to
                # running on, just as in the batched path). Keeps hook-driven
                # runs — snapshot / bottleneck / waveform — from spinning to
                # max_cycles after the last token lands.
                break
        sched_result = cumulative

    sim_time_ps = main_clock.current_time_ps()

    # Invariant verdict.
    checker = SimulationInvariantChecker(
        stat_sink=stat_sink,
        scheduler_result=sched_result,
        simulation_time_ps=sim_time_ps,
    )
    inv_report = checker.run_all(arch)

    # Stall aggregation.
    stall_events = stat_sink.load_stall_history()
    per_module: dict[str, int] = defaultdict(int)
    for e in stall_events:
        per_module[e.module] += e.duration_ps
    total_stall_ps = sum(per_module.values())

    # Bottleneck = trace_chain from the most-stalled module.
    bottleneck = _identify_bottleneck(per_module, stat_sink)

    # Tokens per connection.
    tokens_delivered: dict[str, int] = {}
    tokens_in_flight: dict[str, int] = {}
    drain_time_ps = 0
    for c in arch.connections:
        if isinstance(c.runtime, TlmConnection):
            key = (
                f"{c.spec.source_module}.{c.spec.source_port}→"
                f"{c.spec.sink_module}.{c.spec.sink_port}"
            )
            tokens_delivered[key] = c.runtime.tokens_dequeued
            tokens_in_flight[key] = c.runtime.current_in_flight()
            if c.runtime.last_dequeue_time_ps > drain_time_ps:
                drain_time_ps = c.runtime.last_dequeue_time_ps

    # Area / power aggregation across modules.
    total_area_um2 = sum(m.total_area_um2() for m in arch.modules.values())
    total_static_power_uw = sum(
        m.static_power_uw() for m in arch.modules.values()
    )

    return SimulationResult(
        architecture_name=arch.name,
        cycles_run=sched_result.cycles_run,
        sim_time_ps=sim_time_ps,
        drain_time_ps=drain_time_ps,
        scheduler_result=sched_result,
        invariant_report=inv_report,
        stall_events=tuple(stall_events),
        bottleneck_module=bottleneck,
        total_stall_ps=total_stall_ps,
        per_module_stall_ps=dict(per_module),
        tokens_delivered=tokens_delivered,
        tokens_in_flight=tokens_in_flight,
        total_area_um2=total_area_um2,
        total_static_power_uw=total_static_power_uw,
        elaboration_warnings=tuple(arch.warnings),
    )


# ============================================================
# helpers
# ============================================================


def _make_quiescence_probe(arch, scheduler):
    """Return a predicate: True while the sim may still do work.

    Provably-safe quiescence = (no module busy) AND (no token in any
    connection FIFO) AND (no live *source* generator that could emit).
    A source = a module with output ports and no input ports; once its
    generator finishes it is no longer in ``scheduler.alive_ids()``.
    When this returns False, no future cycle can change any metric.
    """
    conns = [c for c in arch.connections if isinstance(c.runtime, TlmConnection)]
    source_ids = [
        mid for mid, m in arch.modules.items()
        if m.output_ports() and not m.input_ports()
    ]

    def is_active() -> bool:
        for m in arch.modules.values():
            if m.snapshot_state().busy:
                return True
        for c in conns:
            if c.runtime.current_in_flight() > 0:
                return True
        alive = set(scheduler.alive_ids())
        for sid in source_ids:
            if sid in alive:            # a source may still emit
                return True
        return False

    return is_active


def _extract_stat_sink(arch: IArchitecture) -> InMemoryStatSink:
    for module in arch.modules.values():
        sink = getattr(module, "_stat_sink", None)
        if isinstance(sink, InMemoryStatSink):
            return sink
    raise RuntimeError(
        "No InMemoryStatSink found on any module — the architecture must be "
        "elaborated through ArchitectureElaborator before run_simulation()."
    )


def _identify_bottleneck(
    per_module_stall_ps: dict[str, int],
    stat_sink: InMemoryStatSink,
) -> Optional[str]:
    """Pick the module with the most stall time and trace its chain.

    Returns the chain's bottleneck (typically a downstream implicit root).
    If no stalls were recorded, returns None.
    """
    if not per_module_stall_ps:
        return None
    worst = max(per_module_stall_ps, key=per_module_stall_ps.get)
    tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=stat_sink)
    chain = tracer.trace_chain(worst)
    return chain.bottleneck_module


# ============================================================
# Convenience: elaborate + run in one call.
# ============================================================


def elaborate_and_run(
    dsl_path: str,
    max_cycles: int = 10_000,
) -> SimulationResult:
    """One-shot: load DSL, elaborate with fresh services, run, evaluate."""
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
    arch = elab.elaborate(dsl_path)
    return run_simulation(arch, max_cycles=max_cycles)
