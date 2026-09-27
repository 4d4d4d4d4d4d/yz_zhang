"""Unit tests for runtime.TlmConnection. Reference: SPEC-002 §5."""

from __future__ import annotations

from npu_sim.architecture.clock import SimpleClock
from npu_sim.interfaces.transport import ConnectionSpec, TransportToken
from npu_sim.runtime.connection import TlmConnection


def _token(seq: int = 0) -> TransportToken:
    return TransportToken(
        payload=b"x",
        size_bytes=1,
        timestamp_ps=0,
        source_module="src",
        metadata={"seq": seq},
    )


def _make_conn(fifo_depth=2, latency_cycles=1, period_ps=1000):
    spec = ConnectionSpec(
        source_module="src",
        source_port="out",
        sink_module="dst",
        sink_port="in",
        fifo_depth=fifo_depth,
        latency_cycles=latency_cycles,
    )
    clock = SimpleClock("main", period_ps=period_ps)
    return TlmConnection(spec=spec, source_clock=clock), clock


class TestEnqueueDequeue:

    def test_enqueue_blocks_when_full(self):
        conn, _ = _make_conn(fifo_depth=2, latency_cycles=0)
        assert conn.try_enqueue(_token(0))
        assert conn.try_enqueue(_token(1))
        # FIFO full
        assert not conn.try_enqueue(_token(2))

    def test_dequeue_after_latency(self):
        conn, clock = _make_conn(fifo_depth=2, latency_cycles=2, period_ps=1000)
        assert conn.try_enqueue(_token(0))
        # latency = 2 cycles = 2000 ps; not ready at t=0
        assert conn.try_dequeue() is None
        clock.wait_cycles(1)
        assert conn.try_dequeue() is None
        clock.wait_cycles(1)
        # now at t=2000ps — token available
        out = conn.try_dequeue()
        assert out is not None
        assert out.metadata["seq"] == 0

    def test_zero_latency_immediate(self):
        conn, _ = _make_conn(fifo_depth=2, latency_cycles=0)
        assert conn.try_enqueue(_token(0))
        out = conn.try_dequeue()
        assert out is not None

    def test_in_flight_and_utilization(self):
        conn, _ = _make_conn(fifo_depth=4, latency_cycles=0)
        assert conn.utilization() == 0.0
        conn.try_enqueue(_token(0))
        conn.try_enqueue(_token(1))
        assert conn.current_in_flight() == 2
        assert conn.utilization() == 0.5
        conn.try_dequeue()
        assert conn.current_in_flight() == 1
        assert conn.utilization() == 0.25
