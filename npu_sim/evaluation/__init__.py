"""End-to-end evaluation: run a simulation, compare baseline vs variant.

Reference: SPEC-003 §7 R7 (the "AGU-W bandwidth half" archetype).
"""

from typing import Sequence

from npu_sim.architecture.architecture import IArchitecture
from npu_sim.evaluation.comparator import ComparisonReport, compare
from npu_sim.evaluation.numerical_compare import compare_tensors
from npu_sim.evaluation.runner import (
    SimulationResult,
    elaborate_and_run,
    run_simulation,
)
from npu_sim.interfaces.operation import IOperation
from npu_sim.mapping import MappingPlan, RuleBasedMapper


def estimate_plan(
    operations: Sequence[IOperation],
    architecture: IArchitecture,
    strict: bool = True,
) -> MappingPlan:
    """Map ops onto an elaborated architecture using RuleBasedMapper.

    The single integration entry point combining SPEC-006 mapping with the
    SPEC-003 elaborated architecture. Lets a use case produce a static
    estimate (MappingPlan.total_typical_cycles / total_dynamic_pj) alongside
    the dynamic simulation result from `run_simulation`, so estimate vs
    measured can be compared.
    """
    return RuleBasedMapper(strict=strict).map(operations, architecture)


__all__ = [
    "ComparisonReport",
    "MappingPlan",
    "SimulationResult",
    "compare",
    "compare_tensors",
    "elaborate_and_run",
    "estimate_plan",
    "run_simulation",
]
