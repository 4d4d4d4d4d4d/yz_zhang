"""MAC module: Multiply-Accumulate array (timing + functional). SPEC-005 §3."""

from npu_sim.modules.mac.mac_module import MAC
from npu_sim.modules.mac.mac_numerical import MACGoldenModel

__all__ = ["MAC", "MACGoldenModel"]
