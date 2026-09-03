"""Tests for the SPEC-002 §3.5 record_stall legality table."""

from __future__ import annotations

import pytest

from npu_sim.core.errors import InvalidStallReport, MapperBugError
from npu_sim.interfaces.services import (
    InMemoryEventBus,
    InMemoryStatSink,
    StallReason,
)


class TestStallLegality:
    """Enforcement of the SPEC-002 §3.5 reason × caused_by matrix."""

    def _sink(self) -> InMemoryStatSink:
        return InMemoryStatSink(event_bus=InMemoryEventBus())

    # ============== Must HAVE caused_by ==============

    @pytest.mark.parametrize(
        "reason",
        [
            StallReason.OUTPUT_FULL,
            StallReason.OUTPUT_BANDWIDTH,
            StallReason.WAITING_FOR_COMMAND,
            StallReason.WAITING_FOR_SYNC,
        ],
    )
    def test_reason_requires_caused_by(self, reason):
        sink = self._sink()
        with pytest.raises(InvalidStallReport, match="requires caused_by"):
            sink.record_stall(module="A", reason=reason, duration_ps=10, caused_by=None)

    @pytest.mark.parametrize(
        "reason",
        [
            StallReason.OUTPUT_FULL,
            StallReason.OUTPUT_BANDWIDTH,
            StallReason.WAITING_FOR_COMMAND,
            StallReason.WAITING_FOR_SYNC,
        ],
    )
    def test_reason_accepts_with_caused_by(self, reason):
        sink = self._sink()
        sink.record_stall(module="A", reason=reason, duration_ps=10, caused_by="B")
        assert len(sink.load_stall_history()) == 1

    # ============== Must NOT have caused_by ==============

    @pytest.mark.parametrize(
        "reason",
        [
            StallReason.INTERNAL_RESOURCE_CONFLICT,
            StallReason.INTERNAL_PIPELINE_HAZARD,
            StallReason.INTERNAL_CAPACITY,
        ],
    )
    def test_internal_reason_rejects_caused_by(self, reason):
        sink = self._sink()
        with pytest.raises(InvalidStallReport, match="forbids caused_by"):
            sink.record_stall(module="A", reason=reason, duration_ps=10, caused_by="B")

    @pytest.mark.parametrize(
        "reason",
        [
            StallReason.INTERNAL_RESOURCE_CONFLICT,
            StallReason.INTERNAL_PIPELINE_HAZARD,
            StallReason.INTERNAL_CAPACITY,
        ],
    )
    def test_internal_reason_accepts_null_caused_by(self, reason):
        sink = self._sink()
        sink.record_stall(module="A", reason=reason, duration_ps=10, caused_by=None)
        assert len(sink.load_stall_history()) == 1

    # ============== CAPABILITY_MISSING is always a Mapper bug ==============

    def test_capability_missing_raises_mapper_bug(self):
        sink = self._sink()
        with pytest.raises(MapperBugError):
            sink.record_stall(
                module="A",
                reason=StallReason.CAPABILITY_MISSING,
                duration_ps=0,
            )


class TestEventBusPublication:
    """SPEC-002 §3.3.1 Realtime tracer relies on EventBus."""

    def test_record_stall_publishes_event(self):
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)

        received: list[dict] = []
        bus.subscribe("stall.*", received.append)

        sink.record_stall(
            module="A",
            reason=StallReason.OUTPUT_FULL,
            duration_ps=10,
            caused_by="B",
        )

        assert len(received) == 1
        assert received[0]["reason"] == StallReason.OUTPUT_FULL
        assert received[0]["caused_by"] == "B"

    def test_offline_history_matches_realtime_events(self):
        """Both modes must observe the same stream of events."""
        bus = InMemoryEventBus()
        sink = InMemoryStatSink(event_bus=bus)

        realtime: list[dict] = []
        bus.subscribe("stall.*", realtime.append)

        sink.record_stall(module="A", reason=StallReason.OUTPUT_FULL, duration_ps=5, caused_by="B")
        sink.record_stall(
            module="C",
            reason=StallReason.INTERNAL_RESOURCE_CONFLICT,
            duration_ps=3,
        )

        offline = sink.load_stall_history()
        assert len(offline) == len(realtime) == 2
        assert [e.module for e in offline] == [r["module"] for r in realtime]
        assert [e.reason for e in offline] == [r["reason"] for r in realtime]


class TestEventBusWildcards:

    def test_exact_topic_match(self):
        bus = InMemoryEventBus()
        received: list[dict] = []
        bus.subscribe("stall.output_full", received.append)
        bus.publish("stall.output_full", {"hello": 1})
        bus.publish("stall.other", {"hello": 2})
        assert received == [{"hello": 1}]

    def test_glob_topic_match(self):
        bus = InMemoryEventBus()
        received: list[dict] = []
        bus.subscribe("stall.*", received.append)
        bus.publish("stall.output_full", {"a": 1})
        bus.publish("stall.input_empty", {"a": 2})
        bus.publish("counter.x", {"a": 3})
        assert received == [{"a": 1}, {"a": 2}]
