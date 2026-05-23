"""BackpressureTracer end-to-end tests. Reference: SPEC-002 §3.3, §3.3.1, §3.4."""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.interfaces.services import (
    InMemoryEventBus,
    InMemoryStatSink,
    StallReason,
)
from npu_sim.runtime.scheduler import SimpleScheduler
from npu_sim.runtime.tracer import BackpressureTracer, TracerMode
import npu_sim.modules  # noqa: F401  side-effect: registers Producer/Consumer/Passthrough


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _build(fixture_name: str):
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    elab = ArchitectureElaborator(event_bus=bus, stat_sink=sink)
    arch = elab.elaborate(str(FIXTURES / fixture_name))
    main_clock = arch.clocks[next(iter(arch.clocks))]
    sink.bind_clock_fn(main_clock.current_time_ps)
    return arch, bus, sink, main_clock


def _drive(arch, max_cycles=500):
    main_clock = arch.clocks[next(iter(arch.clocks))]
    sched = SimpleScheduler(main_clock)
    for mid, module in arch.modules.items():
        if hasattr(module, "behavior"):
            sched.spawn(module.behavior(), module_id=mid)
    return sched.run(max_cycles=max_cycles)


# ============================================================
# Constructor / mode dispatch (SPEC-002 §3.3.1)
# ============================================================


class TestModeDispatch:

    def test_realtime_requires_event_bus(self):
        sink = InMemoryStatSink(event_bus=InMemoryEventBus())
        with pytest.raises(TypeError, match="REALTIME tracer requires IEventBus"):
            BackpressureTracer(mode=TracerMode.REALTIME, source=sink)

    def test_offline_requires_stat_sink(self):
        bus = InMemoryEventBus()
        with pytest.raises(TypeError, match="OFFLINE tracer requires IStatSink"):
            BackpressureTracer(mode=TracerMode.OFFLINE, source=bus)

    def test_realtime_attaches_subscription(self):
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        tracer = BackpressureTracer(mode=TracerMode.REALTIME, source=bus)
        # Trigger one stall manually
        sink.record_stall(
            module="A",
            reason=StallReason.OUTPUT_FULL,
            duration_ps=100,
            caused_by="B",
        )
        assert len(tracer.events) == 1
        assert tracer.events[0].caused_by == "B"

    def test_offline_loads_snapshot(self):
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        sink.record_stall(
            module="A",
            reason=StallReason.OUTPUT_FULL,
            duration_ps=50,
            caused_by="B",
        )
        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        assert len(tracer.events) == 1

    def test_offline_does_not_see_subsequent_events(self):
        """Offline takes a snapshot at construction time."""
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)
        sink.record_stall("A", StallReason.OUTPUT_FULL, 10, caused_by="B")
        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        # New event after construction
        sink.record_stall("A", StallReason.OUTPUT_FULL, 10, caused_by="B")
        assert len(tracer.events) == 1  # snapshot frozen


# ============================================================
# 2-module chain: prod → cons (slow). Implicit root = cons.
# ============================================================


class TestTwoModuleChain:

    def test_trace_chain_implicates_consumer(self):
        arch, bus, sink, _clock = _build("probe_slow_consumer.yaml")
        _drive(arch, max_cycles=200)

        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        chain = tracer.trace_chain("prod")

        assert chain.end_module == "prod"
        assert chain.total_stall_time_ps > 0
        # Bottleneck must be the slow consumer.
        assert chain.bottleneck_module == "cons"

        # Exactly one implicit root cause (the never-stalling consumer).
        implicit = [c for c in chain.root_causes if c.is_implicit]
        assert len(implicit) == 1
        assert implicit[0].module == "cons"
        assert implicit[0].percentage == pytest.approx(1.0)

        # No explicit (internal) roots in this clean two-module scenario.
        explicit = [c for c in chain.root_causes if not c.is_implicit]
        assert explicit == []

        # Chain links: only prod → cons.
        assert all(l.from_module == "prod" for l in chain.chain_links)
        assert all(l.to_module == "cons" for l in chain.chain_links)
        assert sum(l.contribution_ps for l in chain.chain_links) > 0

    def test_clean_run_empty_chain(self):
        arch, bus, sink, _clock = _build("probe_chain.yaml")
        _drive(arch, max_cycles=100)

        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        chain = tracer.trace_chain("prod")

        assert chain.total_stall_time_ps == 0
        assert chain.root_causes == ()
        assert chain.chain_links == ()
        assert chain.bottleneck_module == "prod"  # falls back to end_module


# ============================================================
# 3-module chain: prod → mid → cons. Bottleneck still cons.
# This is the test referenced in SPEC-002 §6.4.
# ============================================================


class TestThreeModuleChain:

    def test_chain_walks_through_mid_to_cons(self):
        arch, bus, sink, _clock = _build("probe_three_chain.yaml")
        _drive(arch, max_cycles=500)

        # All 8 tokens delivered eventually.
        assert arch.modules["cons"].received == 8

        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        chain = tracer.trace_chain("prod")

        assert chain.total_stall_time_ps > 0
        assert chain.bottleneck_module == "cons"

        # The chain must include both hops.
        link_pairs = {(l.from_module, l.to_module) for l in chain.chain_links}
        assert ("prod", "mid") in link_pairs
        assert ("mid", "cons") in link_pairs

        # involves_module helper sanity.
        assert chain.involves_module("prod")
        assert chain.involves_module("mid")
        assert chain.involves_module("cons")
        assert not chain.involves_module("ghost")


# ============================================================
# Realtime vs Offline parity: same events → same chain.
# ============================================================


class TestModeParity:

    def test_realtime_and_offline_produce_same_chain(self):
        arch, bus, sink, _clock = _build("probe_three_chain.yaml")

        # Attach the realtime tracer BEFORE driving.
        realtime = BackpressureTracer(mode=TracerMode.REALTIME, source=bus)

        _drive(arch, max_cycles=500)

        offline = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)

        chain_rt = realtime.trace_chain("prod")
        chain_off = offline.trace_chain("prod")

        # Both modes saw the same events → bottleneck + total stall match.
        assert chain_rt.bottleneck_module == chain_off.bottleneck_module
        assert chain_rt.total_stall_time_ps == chain_off.total_stall_time_ps
        # Sets of chain link endpoints match too.
        assert {(l.from_module, l.to_module) for l in chain_rt.chain_links} == \
               {(l.from_module, l.to_module) for l in chain_off.chain_links}


# ============================================================
# Time-window filtering.
# ============================================================


class TestTimeWindow:

    def test_window_excludes_pre_window_stalls(self):
        arch, bus, sink, clock = _build("probe_slow_consumer.yaml")
        _drive(arch, max_cycles=200)

        all_events = sink.load_stall_history()
        assert len(all_events) > 0

        # Pick a tight window starting well after all events.
        far_future = (10_000_000, 11_000_000)
        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        chain = tracer.trace_chain("prod", time_window_ps=far_future)

        assert chain.total_stall_time_ps == 0
        assert chain.root_causes == ()


# ============================================================
# §3.4: multi-producer attribution API stability.
# Phase 4: API returns empty list (no producer-side bookkeeping yet).
# ============================================================


class TestMultiProducerApi:

    def test_returns_empty_until_producer_attribution_lands(self):
        arch, bus, sink, _clock = _build("probe_slow_consumer.yaml")
        _drive(arch, max_cycles=200)
        tracer = BackpressureTracer(mode=TracerMode.OFFLINE, source=sink)
        result = tracer.trace_multi_producer_contention("cons")
        assert result == []
