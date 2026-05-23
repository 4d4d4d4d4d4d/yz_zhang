"""End-to-end evaluation: run a simulation, compare baseline vs variant.

Reference: SPEC-003 §7 R7 (the "AGU-W bandwidth half" archetype).
"""

from npu_sim.evaluation.comparator import ComparisonReport, compare
from npu_sim.evaluation.runner import (
    SimulationResult,
    elaborate_and_run,
    run_simulation,
)

__all__ = [
    "ComparisonReport",
    "SimulationResult",
    "compare",
    "elaborate_and_run",
    "run_simulation",
]
