"""SPEC-008 memory & precision modules: WB / OB / Quant / SFU.

Importing this package registers all module types with ModuleRegistry.
"""

from npu_sim.modules.memory.ob_module import OB
from npu_sim.modules.memory.quant_module import Quant
from npu_sim.modules.memory.sfu_module import SFU
from npu_sim.modules.memory.wb_module import WB

__all__ = ["OB", "Quant", "SFU", "WB"]
