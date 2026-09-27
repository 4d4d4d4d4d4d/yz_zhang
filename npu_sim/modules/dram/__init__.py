"""SPEC-011 DRAM subsystem + specialized compute: MC / L2 / SE / TLU / CMDQ / MMU."""

from npu_sim.modules.dram.cmdq_module import CMDQ
from npu_sim.modules.dram.l2_module import L2
from npu_sim.modules.dram.mc_module import MC
from npu_sim.modules.dram.mmu_module import MMU
from npu_sim.modules.dram.se_module import SE
from npu_sim.modules.dram.tlu_module import TLU

__all__ = ["CMDQ", "L2", "MC", "MMU", "SE", "TLU"]
