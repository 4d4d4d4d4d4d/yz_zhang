"""VAU module: Vector Arithmetic Unit (timing + functional). SPEC-005 §4."""

from npu_sim.modules.vau.vau_module import VAU
from npu_sim.modules.vau.vau_numerical import VAUGoldenModel

__all__ = ["VAU", "VAUGoldenModel"]
