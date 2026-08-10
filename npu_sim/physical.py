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


def mux_gates(n_bits: int) -> int:
    """2:1 multiplexer gate count over ``n_bits`` (≈3 gates/bit)."""
    return n_bits * 3


def fp_add_gates(mantissa_bits: int, exp_bits: int = 8) -> int:
    """Floating-point adder: exponent compare + mantissa align-shift + add +
    normalize. Analytical (SPEC-013 §2): mantissa add + 2× mantissa for the
    align/normalize barrel shifters + an exponent adder."""
    return add_gates(mantissa_bits) + 2 * mantissa_bits * _GATES_PER_FA + add_gates(exp_bits)


def fp_mul_gates(mantissa_bits: int, exp_bits: int = 8) -> int:
    """Floating-point multiplier: mantissa array multiply + exponent add +
    normalize."""
    return mult_gates(mantissa_bits) + add_gates(exp_bits) + add_gates(mantissa_bits)


# FP32 datapath: 1 sign + 8 exponent + 23 stored mantissa (24 with implicit 1).
_FP32_MANT = 24


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
    """6T-SRAM *cell* array area (µm²) for ``n_bytes`` of storage."""
    return n_bytes * 8 * A_SRAM_BIT_UM2


# SRAM macro efficiency = cell area / full macro area (decoders + sense amps +
# row/col drivers). Published 45 nm SRAM arrays run ~65–75% efficient.
SRAM_ARRAY_EFFICIENCY = 0.7
# 6T SRAM cell retention leakage @ 45 nm (~0.1 nW/cell order of magnitude).
P_SRAM_LEAK_PER_BIT_UW = 1e-4


def sram_macro_area_um2(n_bytes: float, efficiency: float = SRAM_ARRAY_EFFICIENCY) -> float:
    """Full SRAM macro area (µm²): cell array inflated by peripheral overhead."""
    return sram_area_um2(n_bytes) / efficiency


def sram_read_energy_pj(n_bytes: float) -> float:
    """Energy of an SRAM read of ``n_bytes`` (pJ). Horowitz gives a 32-bit
    (4-byte) SRAM read ≈ 5 pJ; scale linearly with bytes."""
    return E_SRAM_RD_32B_PJ * (n_bytes / 4.0)


def sram_static_power_uw(n_bytes: float) -> float:
    """SRAM retention leakage (µW) for ``n_bytes`` of storage."""
    return n_bytes * 8 * P_SRAM_LEAK_PER_BIT_UW


# ============================================================
# DSB — data-staging buffer (SPEC-013 §5, third migrated module).
# Area/leakage are dominated by the SRAM macro; double-buffering keeps two
# ping-pong copies (2× storage). Energy per staged element is an SRAM read
# (+ a write when double-buffered), replicated across broadcast sinks.
# ============================================================
def dsb_storage_bytes(buffer_kb: int, double_buffer: bool) -> int:
    """Physical SRAM bytes: the buffer, doubled for ping-pong double-buffering."""
    return buffer_kb * 1024 * (2 if double_buffer else 1)


def dsb_area_um2(buffer_kb: int, double_buffer: bool) -> float:
    """DSB area (µm²) = SRAM macro area of the (double-)buffered storage.

    Broadcast wiring and banking overhead are small relative to the SRAM and
    are folded into the macro efficiency factor.
    """
    return sram_macro_area_um2(dsb_storage_bytes(buffer_kb, double_buffer))


def dsb_static_power_uw(buffer_kb: int, double_buffer: bool) -> float:
    """DSB leakage (µW) = SRAM retention leakage of the buffered storage."""
    return sram_static_power_uw(dsb_storage_bytes(buffer_kb, double_buffer))


def dsb_energy_per_elem_pj(
    double_buffer: bool, broadcast_factor: int = 1, bytes_per_elem: int = 2
) -> float:
    """Energy to stage one element (pJ): an SRAM read (+ a write when
    double-buffered), replicated to ``broadcast_factor`` sinks."""
    e = sram_read_energy_pj(bytes_per_elem)
    if double_buffer:
        e += sram_read_energy_pj(bytes_per_elem)   # write side of the ping-pong
    return e * broadcast_factor


# ============================================================
# VAU — vector arithmetic unit (SPEC-013 §5, second migrated module).
# A VAU has `lanes` parallel FP ALUs; each lane carries the logic for every
# op the unit supports, so per-lane gates = Σ active-capability lane logic.
# ============================================================
_VAU_LANE_GATES = {
    "vector_add": fp_add_gates(_FP32_MANT),                 # FP32 adder
    "vector_mul": fp_mul_gates(_FP32_MANT),                 # FP32 multiplier
    "vector_max": fp_add_gates(_FP32_MANT),                 # compare ≈ subtractor
    "relu": mux_gates(32),                                  # max(0,x): sign + 2:1 mux
}

# Energy per element per op @ 45 nm (Horowitz). An element does one op; the
# per-element estimate sums the active ops as a conservative upper bound
# (matches the pre-existing VAU semantics), each term now literature-grounded.
_VAU_ENERGY_PJ = {
    "vector_add": E_ADD_FP32_PJ,     # 0.9
    "vector_mul": E_MUL_FP32_PJ,     # 3.7
    "vector_max": E_ADD_FP32_PJ,     # 0.9  (compare ≈ subtract)
    "relu": E_ADD_INT32_PJ,          # 0.1  (compare-with-0 + select)
}


def vau_lane_gates(active_caps) -> int:
    """Total per-lane gate count for the active VAU capabilities."""
    return sum(_VAU_LANE_GATES.get(c, 0) for c in active_caps)


def vau_area_um2(lanes: int, active_caps) -> float:
    """VAU ALU-array area (µm²): lanes × per-lane gates × gate area."""
    return lanes * vau_lane_gates(active_caps) * A_GATE_UM2


def vau_static_power_uw(lanes: int, active_caps) -> float:
    """VAU leakage (µW): total lane gate count × per-gate leakage."""
    return lanes * vau_lane_gates(active_caps) * P_LEAK_PER_GATE_UW


def vau_energy_per_elem_pj(active_caps) -> float:
    """Dynamic energy per processed element (pJ), summed over active ops."""
    return sum(_VAU_ENERGY_PJ.get(c, 0.0) for c in active_caps)
