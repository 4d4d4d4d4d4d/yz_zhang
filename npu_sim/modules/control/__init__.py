"""SPEC-007 control-plane modules: MCU (Micro Control Unit) + OGU (Op Gen Unit).

Importing this package registers both module types with ModuleRegistry.
"""

from npu_sim.modules.control.mcu_module import MCU
from npu_sim.modules.control.ogu_module import OGU

__all__ = ["MCU", "OGU"]
