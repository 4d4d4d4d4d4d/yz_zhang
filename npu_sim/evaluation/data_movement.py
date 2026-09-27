"""First-order data-movement energy model (SPEC-014).

Real NPU energy is often dominated by moving operands, not by the MACs
themselves (Horowitz: DRAM access 640 pJ vs int MAC ~1 pJ). This attributes,
per op, the energy to read its activations + weights and write its output —
charged at SRAM rate if the working set fits on-chip, or DRAM rate if the
weights spill (the cost of an undersized buffer).

v0.1 is deliberately first-order: no dataflow/tiling/reuse (each op streams
its operands once — a no-reuse upper bound) and no bandwidth roofline. See
SPEC-014 §5 for the v0.2 refinements.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from npu_sim import physical
from npu_sim.architecture.architecture import IArchitecture
from npu_sim.interfaces.operation import IOperation

_PREC_BYTES = {"int4": 1, "int8": 1, "int16": 2, "int32": 4, "fp16": 2,
               "bf16": 2, "fp32": 4, "bfp8": 1, "bfp16": 2, "mixed_bfp8_bfp16": 2}
_MATMUL_OUT_BYTES = 4   # FP32 psum, consistent with SPEC-013 MAC accumulate


def _prec_bytes(op: IOperation) -> int:
    kind = getattr(op.precision, "kind", "fp32")
    # kind is a PrecisionKind enum whose .value is the string name ("int8").
    name = getattr(kind, "value", kind)
    return _PREC_BYTES.get(name, 4)


def op_traffic_bytes(op: IOperation) -> tuple[int, int, int]:
    """(activation_read, weight_read, output_write) bytes for one op (SPEC-014 §1)."""
    shape = dict(op.shape_info)
    p = _prec_bytes(op)
    if op.op_type == "matmul" or ("m" in shape and "k" in shape and "n" in shape):
        m, k, n = shape.get("m", 1), shape.get("k", 1), shape.get("n", 1)
        return (m * k * p, k * n * p, m * n * _MATMUL_OUT_BYTES)
    # elementwise / transcendental: read n, write n; no weights.
    n = shape.get("n_elements", 0)
    return (n * p, 0, n * p)


def onchip_capacity_bytes(architecture: IArchitecture) -> int:
    """Total on-chip buffer capacity (bytes), summed across memory modules
    without depending on fixed module names (SPEC-014 §2)."""
    total = 0
    for m in architecture.modules.values():
        if hasattr(m, "_capacity_bytes"):
            total += int(getattr(m, "_capacity_bytes"))
        elif hasattr(m, "_buffer_kb"):
            total += int(getattr(m, "_buffer_kb")) * 1024
        elif hasattr(m, "_capacity_kb"):
            total += int(getattr(m, "_capacity_kb")) * 1024
        elif hasattr(m, "_tile_kb"):
            total += int(getattr(m, "_tile_kb")) * 1024
    return total


@dataclass(frozen=True)
class DataMovementReport:
    total_pj: float
    weight_dram_pj: float          # portion charged at DRAM rate (spilled weights)
    onchip_capacity_bytes: int
    any_weight_spilled: bool


def data_movement_energy_pj(
    operations: Sequence[IOperation], architecture: IArchitecture
) -> DataMovementReport:
    """Sum per-op data-movement energy (SPEC-014 §3).

    Weights fitting on-chip are read at SRAM rate; weights exceeding the
    on-chip capacity are read from DRAM (the spill penalty). Activations and
    outputs are staged on-chip (SRAM).
    """
    cap = onchip_capacity_bytes(architecture)
    total = 0.0
    weight_dram = 0.0
    spilled = False
    for op in operations:
        act, weight, out = op_traffic_bytes(op)
        total += physical.sram_read_energy_pj(act) + physical.sram_read_energy_pj(out)
        if weight <= cap:
            total += physical.sram_read_energy_pj(weight)
        else:
            e = physical.dram_access_energy_pj(weight)
            total += e
            weight_dram += e
            spilled = True
    return DataMovementReport(
        total_pj=total,
        weight_dram_pj=weight_dram,
        onchip_capacity_bytes=cap,
        any_weight_spilled=spilled,
    )
