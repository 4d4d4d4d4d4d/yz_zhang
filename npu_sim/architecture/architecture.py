"""Architecture: the IArchitecture interface and concrete container.

Reference: SPEC-003 §5 (Elaborator returns IArchitecture).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from npu_sim.architecture.clock import SimpleClock
from npu_sim.interfaces.module import IModule
from npu_sim.interfaces.transport import ConnectionSpec


@dataclass
class ElaboratedConnection:
    """A concrete connection built by the Elaborator.

    Phase 2 (this revision) wires real TlmConnection + port attachment when the
    source / sink modules expose TlmOutput/TlmInput ports; otherwise only the
    spec is recorded (for modules that haven't been ported to real ports yet).
    """

    spec: ConnectionSpec
    source_module: IModule
    sink_module: IModule
    is_cross_domain: bool = False
    runtime: object = None  # TlmConnection when wired; None otherwise


@dataclass
class ElaboratedTopology:
    type: str
    dies: list[dict] = field(default_factory=list)
    inter_die: list[dict] = field(default_factory=list)


class IArchitecture(ABC):
    """The output of an Architecture Elaborator. Reference: SPEC-003 §5."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def metadata(self) -> dict: ...

    @property
    @abstractmethod
    def modules(self) -> dict[str, IModule]: ...

    @property
    @abstractmethod
    def connections(self) -> list[ElaboratedConnection]: ...

    @property
    @abstractmethod
    def clocks(self) -> dict[str, SimpleClock]: ...

    @property
    @abstractmethod
    def topology(self) -> Optional[ElaboratedTopology]: ...

    @property
    @abstractmethod
    def mapping_hints(self) -> dict: ...

    @property
    @abstractmethod
    def warnings(self) -> list[str]:
        """Non-fatal warnings produced during elaboration (SPEC-003 §5 Phase 3.5)."""


@dataclass
class Architecture(IArchitecture):

    _name: str
    _metadata: dict
    _modules: dict[str, IModule]
    _connections: list[ElaboratedConnection]
    _clocks: dict[str, SimpleClock]
    _topology: Optional[ElaboratedTopology]
    _mapping_hints: dict
    _warnings: list[str]

    @property
    def name(self) -> str:
        return self._name

    @property
    def metadata(self) -> dict:
        return self._metadata

    @property
    def modules(self) -> dict[str, IModule]:
        return self._modules

    @property
    def connections(self) -> list[ElaboratedConnection]:
        return self._connections

    @property
    def clocks(self) -> dict[str, SimpleClock]:
        return self._clocks

    @property
    def topology(self) -> Optional[ElaboratedTopology]:
        return self._topology

    @property
    def mapping_hints(self) -> dict:
        return self._mapping_hints

    @property
    def warnings(self) -> list[str]:
        return self._warnings
