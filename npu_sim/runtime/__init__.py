"""Phase 1/2 Python runtime: FIFOs, connections, ports, scheduler, tracer."""

from npu_sim.runtime.connection import TlmConnection
from npu_sim.runtime.fifo import Fifo
from npu_sim.runtime.invariants import (
    IInvariantChecker,
    InvariantFailure,
    InvariantReport,
    InvariantWarning,
    SimulationInvariantChecker,
)
from npu_sim.runtime.ports import TlmInputPort, TlmOutputPort
from npu_sim.runtime.scheduler import SchedulerResult, SimpleScheduler
from npu_sim.runtime.tracer import (
    BackpressureTracer,
    ChainLink,
    MultiProducerContention,
    ProducerActivity,
    StallCause,
    StallChain,
    TracerMode,
)

__all__ = [
    "BackpressureTracer",
    "ChainLink",
    "Fifo",
    "IInvariantChecker",
    "InvariantFailure",
    "InvariantReport",
    "InvariantWarning",
    "MultiProducerContention",
    "ProducerActivity",
    "SchedulerResult",
    "SimpleScheduler",
    "SimulationInvariantChecker",
    "StallCause",
    "StallChain",
    "TlmConnection",
    "TlmInputPort",
    "TlmOutputPort",
    "TracerMode",
]
