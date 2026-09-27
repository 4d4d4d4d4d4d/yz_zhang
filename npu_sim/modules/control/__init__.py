"""SPEC-007 control-plane modules: MCU + OGU + TAU + DMA + MTU + AGU.

Importing this package registers all module types with ModuleRegistry.
"""

from npu_sim.modules.control.agu_module import AGU
from npu_sim.modules.control.dma_module import DMA
from npu_sim.modules.control.mcu_module import MCU
from npu_sim.modules.control.mtu_module import MTU
from npu_sim.modules.control.ogu_module import OGU
from npu_sim.modules.control.tau_module import TAU

__all__ = ["AGU", "DMA", "MCU", "MTU", "OGU", "TAU"]
