"""End-to-end evaluation: run a simulation, compare baseline vs variant.

Reference: SPEC-003 §7 R7 (the "AGU-W bandwidth half" archetype).
"""

from typing import Sequence

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.evaluation.comparator import ComparisonReport, compare
from npu_sim.evaluation.numerical_compare import compare_tensors
from npu_sim.evaluation.runner import (
    SimulationResult,
    elaborate_and_run,
    run_simulation,
)
from npu_sim.evaluation.reconcile import (
    PerOpReconcileReport,
    ReconcileReport,
    reconcile,
    reconcile_per_op,
    sink_op_arrivals,
)
from npu_sim.evaluation.pipeline import (
    PipelineBottleneckReport,
    StageProfile,
    analyze_pipeline_bottleneck,
)
from npu_sim.evaluation.snapshot import (
    ConnectionSnapshot,
    FieldDiff,
    ModuleSnapshot,
    SnapshotDiff,
    StateSnapshot,
    capture_state,
    diff_snapshots,
    snapshot_at_cycle,
)
from npu_sim.evaluation.sweep import SweepPoint, SweepReport, sweep_config
from npu_sim.interfaces.operation import IOperation
from npu_sim.interfaces.services import InMemoryEventBus, InMemoryStatSink
from npu_sim.mapping import MappingPlan, RuleBasedMapper


def elaborate(dsl_path: str) -> IArchitecture:
    """Elaborate a DSL file with fresh services. The single entry point
    for use cases that need to inspect the elaborated architecture
    (capabilities, modules, topology) without running the simulator.

    Pair with :func:`run_simulation` for explicit sim invocations or use
    :func:`elaborate_and_run` for one-shot eval. Keeps evaluation code
    YAML-driven by hiding event_bus / stat_sink wiring.
    """
    bus = InMemoryEventBus()
    sink = InMemoryStatSink(event_bus=bus)
    return ArchitectureElaborator(event_bus=bus, stat_sink=sink).elaborate(dsl_path)


def estimate_plan(
    operations: Sequence[IOperation],
    architecture: IArchitecture,
    strict: bool = True,
) -> MappingPlan:
    """Map ops onto an elaborated architecture using RuleBasedMapper."""
    return RuleBasedMapper(strict=strict).map(operations, architecture)


__all__ = [
    "ComparisonReport",
    "ConnectionSnapshot",
    "FieldDiff",
    "MappingPlan",
    "ModuleSnapshot",
    "PerOpReconcileReport",
    "PipelineBottleneckReport",
    "ReconcileReport",
    "SimulationResult",
    "SnapshotDiff",
    "StageProfile",
    "StateSnapshot",
    "SweepPoint",
    "SweepReport",
    "analyze_pipeline_bottleneck",
    "capture_state",
    "compare",
    "compare_tensors",
    "diff_snapshots",
    "sweep_config",
    "elaborate",
    "elaborate_and_run",
    "estimate_plan",
    "reconcile",
    "reconcile_per_op",
    "run_simulation",
    "sink_op_arrivals",
    "snapshot_at_cycle",
]
