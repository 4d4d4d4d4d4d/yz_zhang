"""IClock: time abstraction injected via IModule.bind_services().

Reference: SPEC-001 §3.3.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class IClockEvent:
    """An event within a clock domain. Concrete type defined by implementation."""

    name: str
    domain_id: str


class IClock(ABC):
    """Module's view of simulated time.

    The only time source a module may consult. No `time.time()`, no global
    SystemC time reads from inside a module.
    """

    @property
    @abstractmethod
    def domain_id(self) -> str:
        """Identifier of the clock domain (matches DSL clock_domains.id)."""

    @property
    @abstractmethod
    def period_ps(self) -> int:
        """Clock period in picoseconds."""

    @abstractmethod
    def current_time_ps(self) -> int:
        """Current simulated time in picoseconds (global timeline). Side-effect free."""

    @abstractmethod
    def current_cycle(self) -> int:
        """Current cycle count within this domain. == current_time_ps // period_ps."""

    @abstractmethod
    def wait_cycles(self, n: int) -> None:
        """Suspend the calling SC_THREAD for n cycles. Time advances."""

    @abstractmethod
    def wait_until_ps(self, target_time_ps: int) -> None:
        """Suspend until the given time. Must satisfy target >= current_time_ps()."""

    @abstractmethod
    def wait_event(self, event: IClockEvent) -> None:
        """Suspend until the given event triggers."""

    @abstractmethod
    def is_same_domain(self, other: "IClock") -> bool:
        """True iff `other` has the same domain_id and period_ps.

        Used by ITransportPort to decide whether a connection needs CDC FIFO
        insertion. Reference: SPEC-002 §5.1.
        """
