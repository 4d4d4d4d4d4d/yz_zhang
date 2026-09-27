"""SimulationInvariantChecker end-to-end tests. Reference: SPEC-002 §7."""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.interfaces.services import (
    InMemoryEventBus,
    InMemoryStatSink,
    StallEvent,
    StallReason,
)
from npu_sim.runtime.invariants import (
    InvariantFailure,
    InvariantReport,
    SimulationInvariantChecker,
)
from npu_sim.runtime.scheduler import SchedulerResult, SimpleScheduler
import npu_sim.modules  # noqa: F401  register all probe modules


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _build_and_run(fixture_name: str, max_cycles: int = 500):
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
    arch = elab.elaborate(str(FIXTURES / fixture_name))
    main_clock = arch.clocks[next(iter(arch.clocks))]
    sink.bind_clock_fn(main_clock.current_time_ps)

    sched = SimpleScheduler(main_clock)
    for mid, module in arch.modules.items():
        if hasattr(module, "behavior"):
            sched.spawn(module.behavior(), module_id=mid)
    result = sched.run(max_cycles=max_cycles)

    sim_time_ps = main_clock.current_time_ps()
    checker = SimulationInvariantChecker(
        stat_sink=sink,
        scheduler_result=result,
        simulation_time_ps=sim_time_ps,
    )
    return arch, sink, result, checker


# ============================================================
# Clean drainable run → all invariants pass.
# ============================================================


class TestCleanRun:

    def test_clean_run_is_valid(self):
        arch, sink, result, checker = _build_and_run("probe_chain.yaml")
        report = checker.run_all(arch)
        assert report.overall_valid, report.summary_text
        assert report.failures == ()
        assert "VALID" in report.summary_text

    def test_slow_consumer_still_drains_and_is_valid(self):
        arch, sink, result, checker = _build_and_run("probe_slow_consumer.yaml")
        report = checker.run_all(arch)
        assert report.overall_valid, report.summary_text
        assert report.failures == ()


# ============================================================
# Deadlock → INV-3 fails.
# ============================================================


class TestDeadlockDetection:

    def test_never_consume_run_is_invalid(self):
        # FIFO depth 2; producer of 8 tokens; consumer never_consume=true.
        # Producer's send() blocks forever; scheduler hits max_cycles with a
        # surviving behavior. INV-3 must fire.
        arch, sink, result, checker = _build_and_run(
            "probe_never_consume.yaml", max_cycles=50
        )
        report = checker.run_all(arch)
        assert not report.overall_valid
        ids = {f.invariant_id for f in report.failures}
        assert "INV-3" in ids
        # INV-2 also fails because tokens remain in flight.
        assert "INV-2" in ids


# ============================================================
# Targeted failure injection — unit-style checks per invariant.
# ============================================================


def _empty_arch():
    """Build an empty architecture to feed targeted invariant probes."""
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
    # Reuse the smallest valid fixture and ignore the modules / events.
    arch = elab.elaborate(str(FIXTURES / "probe_chain.yaml"))
    return arch, sink


class TestInv5Monotonic:

    def test_out_of_order_events_fail_inv5(self):
        arch, sink = _empty_arch()
        # Inject events with non-monotonic time order.
        sink._stalls.append(StallEvent(
            time_ps=1000, module="prod", reason=StallReason.OUTPUT_FULL,
            duration_ps=100, caused_by="cons",
        ))
        sink._stalls.append(StallEvent(
            time_ps=500,  module="prod", reason=StallReason.OUTPUT_FULL,
            duration_ps=100, caused_by="cons",
        ))
        result = SchedulerResult(cycles_run=10, finished=0, deadlocked=0)
        checker = SimulationInvariantChecker(sink, result, simulation_time_ps=2000)
        report = checker.run_all(arch)
        assert "INV-5" in {f.invariant_id for f in report.failures}


class TestInv6CausedByValid:

    def test_unknown_caused_by_fails_inv6(self):
        arch, sink = _empty_arch()
        sink._stalls.append(StallEvent(
            time_ps=100, module="prod", reason=StallReason.OUTPUT_FULL,
            duration_ps=50, caused_by="ghost_module",
        ))
        result = SchedulerResult(cycles_run=10, finished=0, deadlocked=0)
        checker = SimulationInvariantChecker(sink, result, simulation_time_ps=500)
        report = checker.run_all(arch)
        failures = {f.invariant_id: f for f in report.failures}
        assert "INV-6" in failures
        assert failures["INV-6"].evidence["total"] == 1


class TestInv4ChainCycle:

    def test_cycle_fails_inv4(self):
        arch, sink = _empty_arch()
        # Build a 2-cycle: prod blames cons, cons blames prod.
        # (cons recording OUTPUT_FULL caused_by prod is unusual but possible
        # if both are sending into each other.)
        sink._stalls.append(StallEvent(
            time_ps=10, module="prod", reason=StallReason.OUTPUT_FULL,
            duration_ps=10, caused_by="cons",
        ))
        sink._stalls.append(StallEvent(
            time_ps=20, module="cons", reason=StallReason.OUTPUT_FULL,
            duration_ps=10, caused_by="prod",
        ))
        result = SchedulerResult(cycles_run=10, finished=0, deadlocked=0)
        checker = SimulationInvariantChecker(sink, result, simulation_time_ps=100)
        report = checker.run_all(arch)
        assert "INV-4" in {f.invariant_id for f in report.failures}


class TestWarningsBoundaries:

    def test_long_chain_emits_w1(self):
        arch, sink = _empty_arch()
        # Chain m0 → m1 → m2 → ... → m9 (depth 9, exceeds advisory 8).
        # Manually populate stall events; INV-W1 only inspects the graph.
        for i in range(9):
            sink._stalls.append(StallEvent(
                time_ps=10 * (i + 1),
                module=f"m{i}",
                reason=StallReason.OUTPUT_FULL,
                duration_ps=5,
                caused_by=f"m{i + 1}",
            ))
        result = SchedulerResult(cycles_run=100, finished=0, deadlocked=0)
        checker = SimulationInvariantChecker(sink, result, simulation_time_ps=1000)
        report = checker.run_all(arch)
        warning_ids = {w.invariant_id for w in report.warnings}
        assert "INV-W1" in warning_ids
        # ... but caused_by refs unknown modules → INV-6 still fails;
        # invalidity should be reported and the warning should remain.
        assert not report.overall_valid

    def test_stall_ratio_above_threshold_emits_w2(self):
        arch, sink = _empty_arch()
        # Module prod stalls for 950 of 1000 ps (95% > 90%).
        sink._stalls.append(StallEvent(
            time_ps=50, module="prod", reason=StallReason.OUTPUT_FULL,
            duration_ps=950, caused_by="cons",
        ))
        result = SchedulerResult(cycles_run=1000, finished=0, deadlocked=0)
        checker = SimulationInvariantChecker(sink, result, simulation_time_ps=1000)
        report = checker.run_all(arch)
        assert "INV-W2" in {w.invariant_id for w in report.warnings}


# ============================================================
# Report formatting sanity.
# ============================================================


class TestReportFormatting:

    def test_valid_summary_has_no_warnings_when_clean(self):
        arch, sink, result, checker = _build_and_run("probe_chain.yaml")
        report = checker.run_all(arch)
        assert "VALID" in report.summary_text
        assert "All invariants passed" in report.summary_text

    def test_invalid_summary_lists_failures(self):
        arch, sink, result, checker = _build_and_run(
            "probe_never_consume.yaml", max_cycles=20
        )
        report = checker.run_all(arch)
        assert "INVALID" in report.summary_text
        assert "INV-3" in report.summary_text or "INV-2" in report.summary_text
