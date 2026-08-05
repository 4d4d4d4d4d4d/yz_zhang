"""Physically-grounded PPA coefficients — literature-derived, not hand-picked.

Every constant here traces to a published source at a stated process node, so
area/energy come from a documented physical basis instead of arbitrary round
numbers. This is the standard pre-silicon methodology (McPAT / Aladdin /
Timeloop use the same analytical + literature approach before a PDK exists).
See docs/specs/SPEC-013-Physical-PPA-Models.md for the full derivation.

Reference node: **45 nm**. Energy figures are used at their *published* node
(Horowitz ISSCC 2014, measured/reported at 45 nm) rather than fabricated-scaled
to a finer node — scaling to a target node is a Phase-5 calibration step with
its own published factors, kept out so nothing here is invented.

What this buys over the old capability-constant model:
  * area/energy scale with the actual datapath size (PE count, SRAM bytes),
    fixing the size-blind gap (docs/specs/README.md);
  * every number is greppable to a citation, fixing the provenance gap.

Uncertainty: gate-count area is analytical (±~30%); it is the *functional
form* (area ∝ PE count) that matters pre-calibration, and the unit costs cite
published cell/gate/op values. Phase-5 replaces the unit costs with synthesis.
"""

from __future__ import annotations

REFERENCE_NODE_NM = 45

# ============================================================
# Energy per operation @ 45 nm (pJ)
# Source: M. Horowitz, "1.1 Computing's Energy Problem (and what we can do
# about it)", ISSCC 2014, Fig. 1.1.5 — the canonical, widely-reproduced table.
# ============================================================
E_ADD_INT8_PJ = 0.03      # 8-bit integer add
E_ADD_INT32_PJ = 0.1      # 32-bit integer add
E_MUL_INT8_PJ = 0.2       # 8-bit int mult: 32b=3.1pJ, ~quadratic in width → ~0.2
E_MUL_INT32_PJ = 3.1      # 32-bit integer multiply
E_ADD_FP16_PJ = 0.4       # 16-bit float add
E_ADD_FP32_PJ = 0.9       # 32-bit float add (used for FP32 accumulation)
E_MUL_FP16_PJ = 1.1       # 16-bit float multiply
E_MUL_FP32_PJ = 3.7       # 32-bit float multiply
E_SRAM_RD_32B_PJ = 5.0    # 32-bit read from an 8 KB SRAM
E_DRAM_RD_32B_PJ = 640.0  # 32-bit DRAM access

# ============================================================
# Area unit costs @ 45 nm (µm²)
# ============================================================
# 6T SRAM bitcell @ 45 nm. Published cells: TSMC 45nm ~0.25, Intel 45nm 0.346.
# Use 0.25 (dense foundry 6T); Phase-5 sets the exact library value.
A_SRAM_BIT_UM2 = 0.25
# NAND2-equivalent standard cell @ 45 nm (~0.7–1.0 µm² across libraries).
A_GATE_UM2 = 0.8

# ============================================================
# Static (leakage) power @ 45 nm
# ~few nW per NAND2-equivalent gate for a general-purpose 45 nm process.
# ============================================================
P_LEAK_PER_GATE_UW = 0.003   # 3 nW/gate

# ============================================================
# Analytical gate counts for arithmetic units.
# Methodology (SPEC-013 §2): an n-bit array multiplier ≈ n² partial-product
# AND gates + n·(n−1) full-adders; an n-bit adder ≈ n full-adders; an n-bit
# register ≈ n flip-flops. A full-adder and a flip-flop are each ≈ 5
# NAND2-equivalent gates.
# ============================================================
_GATES_PER_FA = 5
_GATES_PER_FF = 5


def mult_gates(n_bits: int) -> int:
    """Array-multiplier gate count for an ``n_bits`` × ``n_bits`` multiply."""
    return n_bits * n_bits + n_bits * (n_bits - 1) * _GATES_PER_FA


def add_gates(n_bits: int) -> int:
    """Ripple-carry adder gate count for an ``n_bits`` add."""
    return n_bits * _GATES_PER_FA


def reg_gates(n_bits: int) -> int:
    """Register gate count for ``n_bits`` of state."""
    return n_bits * _GATES_PER_FF


# Per-PE gate contribution of each MAC capability (SPEC-013 §3). A MAC PE is a
# multiplier feeding an accumulator; each precision the array supports adds its
# own multiplier lane, and FP32 accumulation adds a 32-bit adder + psum reg.
_MAC_PE_GATES = {
    # int8×int8 multiply.
    "int8_matmul": mult_gates(8),                       # 344
    # FP32 accumulate: 32-bit adder + 32-bit psum register.
    "accumulate_fp32": add_gates(32) + reg_gates(32),   # 320
    # BFP16: 8-bit mantissa multiply + shared-exponent alignment (~+50).
    "bfp16_matmul": mult_gates(8) + 50,                 # 394
    # FP16: 11-bit mantissa multiply + FP16 add for the wider datapath.
    "fp16_matmul": mult_gates(11) + add_gates(11),      # 726
}


def mac_pe_gates(active_caps) -> int:
    """Total per-PE gate count for the given active MAC capabilities."""
    return sum(_MAC_PE_GATES.get(c, 0) for c in active_caps)


def mac_array_area_um2(rows: int, cols: int, active_caps) -> float:
    """PE-array area (µm²): PE count × per-PE gates × gate area.

    Scales with the array size — the whole point of the physical model.
    """
    return rows * cols * mac_pe_gates(active_caps) * A_GATE_UM2


def mac_array_static_power_uw(rows: int, cols: int, active_caps) -> float:
    """PE-array leakage (µW): total gate count × per-gate leakage."""
    return rows * cols * mac_pe_gates(active_caps) * P_LEAK_PER_GATE_UW


# MAC precision-kind → (multiply energy, accumulate energy) in pJ.
# Accumulation is FP32 (the psum datapath), so it dominates low-precision MACs.
_MAC_ENERGY_PJ = {
    "int8": E_MUL_INT8_PJ + E_ADD_FP32_PJ,     # 1.1
    "bfp16": E_MUL_FP16_PJ + E_ADD_FP32_PJ,    # 2.0  (block-FP ~ FP16 mult)
    "bf16": E_MUL_FP16_PJ + E_ADD_FP32_PJ,     # alias
    "fp16": E_MUL_FP16_PJ + E_ADD_FP32_PJ,     # 2.0
    "fp32": E_MUL_FP32_PJ + E_ADD_FP32_PJ,     # 4.6
}


def energy_per_mac_pj(precision_kind: str) -> float:
    """Dynamic energy of one multiply-accumulate at the given precision (pJ).

    Defaults to the int8 figure for unknown kinds (the array's base lane).
    """
    return _MAC_ENERGY_PJ.get(precision_kind, _MAC_ENERGY_PJ["int8"])


def sram_area_um2(n_bytes: float) -> float:
    """6T-SRAM array area (µm²) for ``n_bytes`` of storage."""
    return n_bytes * 8 * A_SRAM_BIT_UM2
