"""SPEC-008 memory & precision modules: WB (Weight Buffer).

Importing this package registers all module types with ModuleRegistry.
Future §§: OB, Quant, SFU.
"""

from npu_sim.modules.memory.wb_module import WB

__all__ = ["WB"]
