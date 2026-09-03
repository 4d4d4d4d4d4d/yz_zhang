"""DAGC module: BFP unpack / data-alignment controller (timing + functional)."""

from npu_sim.modules.dagc.dagc_module import DAGC
from npu_sim.modules.dagc.dagc_numerical import DAGCGoldenModel

__all__ = ["DAGC", "DAGCGoldenModel"]
