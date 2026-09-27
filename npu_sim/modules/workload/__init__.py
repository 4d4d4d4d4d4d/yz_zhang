"""SPEC-009 workload-shape + interconnect modules: IM2COL / RDC / NoC / CDE / Transpose."""

from npu_sim.modules.workload.cde_module import CDE
from npu_sim.modules.workload.im2col_module import IM2COL
from npu_sim.modules.workload.noc_module import NoC
from npu_sim.modules.workload.rdc_module import RDC
from npu_sim.modules.workload.transpose_module import Transpose

__all__ = ["CDE", "IM2COL", "NoC", "RDC", "Transpose"]
