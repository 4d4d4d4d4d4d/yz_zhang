"""TlmOutputPort / TlmInputPort: Python-native ITransportPort implementations.

Reference: SPEC-002 §3.

Phase 2 conventions:
- `send()` (per the spec) is conceptually blocking. In Python, blocking is
  implemented via a generator helper: modules use `yield from port.send(token)`.
- `try_send()` (per spec) is non-blocking and returns BACKPRESSURE immediately.
- Stall on output backpressure is automatically reported with caused_by =
  sink module id, per SPEC-002 §3.5 and ADR-001.5.
"""

from __future__ import annotations

from typing import Callable, Iterator, Optional

from npu_sim.interfaces.clock import IClock
from npu_sim.interfaces.services import IStatSink, StallReason
from npu_sim.interfaces.transport import (
    ITransportPort,
    PortDirection,
    PortSpec,
    ReceiveResult,
    TransportResult,
    TransportStatus,
    TransportToken,
)
from npu_sim.runtime.connection import TlmConnection


class TlmOutputPort(ITransportPort):

    def __init__(
        self,
        port_spec: PortSpec,
        owner_module_id: str,
        clock: IClock,
        stat_sink: IStatSink,
    ) -> None:
        if port_spec.direction != PortDirection.OUTPUT:
            raise ValueError(
                f"TlmOutputPort requires PortDirection.OUTPUT; got {port_spec.direction}."
            )
        self._spec = port_spec
        self._owner = owner_module_id
        self._clock = clock
        self._stat_sink = stat_sink
        self._connection: Optional[TlmConnection] = None
        self._sink_module_id: Optional[str] = None

    # ============== wiring (called by Elaborator / tests) ==============

    def attach(self, connection: TlmConnection, sink_module_id: str) -> None:
        self._connection = connection
        self._sink_module_id = sink_module_id

    # ============== ITransportPort metadata ==============

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def direction(self) -> PortDirection:
        return self._spec.direction

    @property
    def owner_module(self) -> str:
        return self._owner

    # ============== synchronous (non-blocking) attempts ==============

    def try_send(self, token: TransportToken) -> TransportResult:
        if self._connection is None:
            raise RuntimeError(
                f"OutputPort {self._owner}.{self.name} has no connection attached."
            )
        if self._connection.try_enqueue(token):
            return TransportResult(
                status=TransportStatus.OK,
                accepted_at_ps=self._clock.current_time_ps(),
                stall_duration_ps=0,
            )
        return TransportResult(
            status=TransportStatus.BACKPRESSURE,
            stall_duration_ps=0,
            stall_cause_module=self._sink_module_id,
        )

    def ready_to_send(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.current_in_flight() < self._connection.spec().fifo_depth

    # ============== blocking generator (Phase 2 Python convention) ==============

    def send(self, token: TransportToken) -> Iterator[None]:
        """Generator implementation of SPEC-002 §3.2 blocking send().

        Usage in a module behavior:

            yield from self._out_port.send(token)

        Yields one cycle each time the downstream FIFO is full. On return, the
        token has been accepted by the connection. If any cycles were spent
        waiting, a single stall event is recorded with the aggregate duration
        and caused_by = sink module id (SPEC-002 §3.5 / ADR-001.5).
        """
        if self._connection is None:
            raise RuntimeError(
                f"OutputPort {self._owner}.{self.name} has no connection attached."
            )

        start_ps = self._clock.current_time_ps()
        while not self._connection.try_enqueue(token):
            yield  # blocked; let scheduler advance one cycle
        end_ps = self._clock.current_time_ps()

        stall_duration_ps = end_ps - start_ps
        if stall_duration_ps > 0:
            self._stat_sink.record_stall(
                module=self._owner,
                reason=StallReason.OUTPUT_FULL,
                duration_ps=stall_duration_ps,
                caused_by=self._sink_module_id,
                details={
                    "port": self.name,
                    "downstream_fifo_capacity": self._connection.spec().fifo_depth,
                },
            )

    # ============== INPUT-port API is invalid for an OUTPUT port ==============

    def on_receive(self, handler: Callable[[TransportToken], ReceiveResult]) -> None:
        raise RuntimeError("OutputPort cannot register a receive handler.")

    def fifo_level(self) -> int:
        return 0

    def fifo_capacity(self) -> int:
        return 0


class TlmInputPort(ITransportPort):

    def __init__(
        self,
        port_spec: PortSpec,
        owner_module_id: str,
        clock: IClock,
    ) -> None:
        if port_spec.direction != PortDirection.INPUT:
            raise ValueError(
                f"TlmInputPort requires PortDirection.INPUT; got {port_spec.direction}."
            )
        self._spec = port_spec
        self._owner = owner_module_id
        self._clock = clock
        self._connection: Optional[TlmConnection] = None

    def attach(self, connection: TlmConnection) -> None:
        self._connection = connection

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def direction(self) -> PortDirection:
        return self._spec.direction

    @property
    def owner_module(self) -> str:
        return self._owner

    def fifo_level(self) -> int:
        return self._connection.current_in_flight() if self._connection else 0

    def fifo_capacity(self) -> int:
        return self._connection.spec().fifo_depth if self._connection else 0

    # ============== Phase 2 polling helper ==============

    def try_receive(self) -> Optional[TransportToken]:
        """Non-blocking receive. Returns the next ready token, or None."""
        if self._connection is None:
            return None
        return self._connection.try_dequeue()

    # ============== INPUT port: send-side API invalid ==============

    def send(self, token: TransportToken) -> TransportResult:
        raise RuntimeError("InputPort cannot send.")

    def try_send(self, token: TransportToken) -> TransportResult:
        raise RuntimeError("InputPort cannot try_send.")

    def ready_to_send(self) -> bool:
        return False

    def on_receive(self, handler: Callable[[TransportToken], ReceiveResult]) -> None:
        # Phase 2 modules use polling via try_receive(); callback-style is
        # not implemented until SystemC integration.
        raise NotImplementedError(
            "on_receive(handler) is not implemented in the Python-only path; "
            "use try_receive() from a generator behavior."
        )
