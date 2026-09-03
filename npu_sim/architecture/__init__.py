"""Architecture description: DSL loading, override merging, elaboration."""

from npu_sim.architecture.architecture import (
    Architecture,
    ElaboratedConnection,
    ElaboratedTopology,
    IArchitecture,
)
from npu_sim.architecture.clock import SimpleClock
from npu_sim.architecture.dsl_schema import DSL_SCHEMA
from npu_sim.architecture.elaborator import ArchitectureElaborator
from npu_sim.architecture.loader import load_dsl
from npu_sim.architecture.overrides import apply_overrides

__all__ = [
    "Architecture",
    "ArchitectureElaborator",
    "DSL_SCHEMA",
    "ElaboratedConnection",
    "ElaboratedTopology",
    "IArchitecture",
    "SimpleClock",
    "apply_overrides",
    "load_dsl",
]
