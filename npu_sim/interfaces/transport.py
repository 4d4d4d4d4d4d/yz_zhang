"""ITransportPort and connection abstractions.

Reference: SPEC-002 §3.1, §5.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Union


class PortDirection(Enum):
    INPUT = "in"
    OUTPUT = "out"


class DataType(Enum):
    COMMAND = "cmd"
    DATA = "data"
    RESPONSE = "resp"
    CONTROL = "ctrl"


class TransportStatus(Enum):
    OK = "ok"
    BACKPRESSURE = "backpressure"
    ERROR = "error"
    TIMEOUT = "timeout"


class ReceiveDecision(Enum):
    ACCEPTED = "accepted"
    DEFERRED = "deferred"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TransportToken:
    """A transport unit. Reference: SPEC-002 §3.1."""

    payload: Union[bytes, dict]
    size_bytes: int
    timestamp_ps: int
    source_module: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TransportResult:
    status: TransportStatus
    accepted_at_ps: Optional[int] = None
    stall_duration_ps: int = 0
    stall_cause_module: Optional[str] = None


@dataclass(frozen=True)
class ReceiveResult:
    decision: ReceiveDecision
    defer_cycles: int = 0
    reject_reason: str = ""


@dataclass(frozen=True)
class PortSpec:
    """Module port specification. Reference: SPEC-001 §3.1."""

    name: str
    direction: PortDirection
    data_type: DataType
    width_bits: int
    fifo_depth: int


class ITransportPort(ABC):
    """A module port. All inter-module communication goes through this interface.

    Reference: SPEC-002 §3.1.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def direction(self) -> PortDirection: ...

    @property
    @abstractmethod
    def owner_module(self) -> str:
        """Owning module id. Used for backpressure attribution (SPEC-002 §3.3)."""

    # OUTPUT port API

    @abstractmethod
    def send(self, token: TransportToken) -> TransportResult:
        """Blocking send. Returns when downstream has accepted the token.

        Backpressure is produced automatically; stall_duration_ps reflects how
        long the calling module was suspended. Reference: SPEC-002 §3.2.
        """

    @abstractmethod
    def try_send(self, token: TransportToken) -> TransportResult:
        """Non-blocking send. Returns BACKPRESSURE immediately if downstream is busy."""

    @abstractmethod
    def ready_to_send(self) -> bool: ...

    # INPUT port API

    @abstractmethod
    def on_receive(self, handler: Callable[[TransportToken], ReceiveResult]) -> None: ...

    @abstractmethod
    def fifo_level(self) -> int: ...

    @abstractmethod
    def fifo_capacity(self) -> int: ...


@dataclass(frozen=True)
class ConnectionSpec:
    """Connection specification declared in the architecture DSL.

    Reference: SPEC-002 §5, SPEC-003 §3.1.
    """

    source_module: str
    source_port: str
    sink_module: str
    sink_port: str
    fifo_depth: int
    latency_cycles: int
    bandwidth_gbps: float = 0.0


@dataclass(frozen=True)
class CdcConnectionSpec(ConnectionSpec):
    """Cross-domain connection (auto-inserted by Elaborator when source.domain != sink.domain).

    Reference: SPEC-002 §5.1.
    """

    source_domain: str = ""
    sink_domain: str = ""
    sync_stages: int = 2
    async_fifo_depth: int = 8
    metastability_model: str = "none"


class IConnection(ABC):
    """A live connection between two modules. Reference: SPEC-002 §5."""

    @abstractmethod
    def spec(self) -> ConnectionSpec: ...

    @abstractmethod
    def current_in_flight(self) -> int: ...

    @abstractmethod
    def utilization(self) -> float: ...
