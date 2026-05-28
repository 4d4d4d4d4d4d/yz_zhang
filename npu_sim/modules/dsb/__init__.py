"""DSB module: Data Staging Buffer (timing + functional). SPEC-005 §2."""

from npu_sim.modules.dsb.dsb_module import DSB
from npu_sim.modules.dsb.dsb_numerical import DSBGoldenModel

__all__ = ["DSB", "DSBGoldenModel"]
