"""Validation: does the physical model produce plausible ABSOLUTE numbers?

The strongest answer to "is this real?" — cross-check physical.py's outputs
against published references at 45 nm. These are deliberately *range* checks
(not exact), because the model is a ±30% analytical estimate; the point is
that it lands in the right ballpark against real silicon/literature, so the
absolute figures are grounded, not fabricated.

References:
  * Horowitz, ISSCC 2014 — energy per op @ 45 nm.
  * 45 nm 6T SRAM macro density ~2.5–4.0k µm²/KB (foundry SRAM compilers).
  * int8 MAC unit ~500–1000 NAND2-equiv gates; FP32 multiply ~3–5k gates
    (standard arithmetic-unit gate counts).
  * A 45 nm MAC cell ~500–1000 µm² → ~0.5–1 mm² for a 1024-MAC array.
"""

from __future__ import annotations

from npu_sim import physical as P


class TestEnergyPlausible:
    def test_per_mac_energy_in_range(self):
        # int8 mult + FP32 accumulate, Horowitz @45nm.
        assert 0.8 <= P.energy_per_mac_pj("int8") <= 1.5
        assert P.energy_per_mac_pj("fp16") > P.energy_per_mac_pj("int8")

    def test_sram_read_energy_per_byte_in_range(self):
        # Horowitz 32b SRAM read ~5 pJ → ~1.25 pJ/byte.
        per_byte = P.sram_read_energy_pj(1)
        assert 1.0 <= per_byte <= 1.5


class TestAreaPlausible:
    def test_sram_density_matches_published_45nm(self):
        # 45 nm 6T SRAM macro: ~2.5–4.0k µm²/KB.
        assert 2500 <= P.cache_area_um2(1) <= 4000

    def test_int8_mac_pe_gate_count_in_range(self):
        # int8 multiply + FP32 accumulate PE ~500–1000 gates.
        gates = P.mac_pe_gates(["int8_matmul", "accumulate_fp32"])
        assert 500 <= gates <= 1000

    def test_per_mac_area_in_range(self):
        # A 45 nm MAC cell ~500–1000 µm².
        per_mac = P.mac_array_area_um2(1, 1, ["int8_matmul", "accumulate_fp32"])
        assert 400 <= per_mac <= 1000

    def test_1024_mac_array_area_in_range(self):
        # 32×32 = 1024 int8 MACs ~0.5–1.0 mm².
        mm2 = P.mac_array_area_um2(32, 32, ["int8_matmul", "accumulate_fp32"]) / 1e6
        assert 0.4 <= mm2 <= 1.0

    def test_fp32_multiplier_gate_count_in_range(self):
        # Textbook FP32 multiply ~3–5k NAND2-equiv gates.
        assert 3000 <= P.fp_mul_gates(24) <= 5000

    def test_edram_denser_than_sram_by_published_factor(self):
        # eDRAM (1T1C) ~3–5× denser than 6T SRAM.
        ratio = P.A_SRAM_BIT_UM2 / P.A_EDRAM_BIT_UM2
        assert 3.0 <= ratio <= 5.0
