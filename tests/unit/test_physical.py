"""Physical PPA model — literature-grounded coefficients (SPEC-013 §T.1).

Pins each constant to its cited value and verifies the physical scaling laws
(area/leakage ∝ PE count, monotone in precision-lane count). This is the
"not imagined" guarantee: the numbers match Horowitz ISSCC'14 / published cell
areas, and the functional form is physically correct.
"""

from __future__ import annotations

import pytest

from npu_sim import physical as P


class TestEnergyMatchesHorowitz:
    """SPEC-013 §1 — Horowitz ISSCC 2014 Fig. 1.1.5 @ 45nm."""

    def test_op_energies(self):
        assert P.E_ADD_INT8_PJ == 0.03
        assert P.E_ADD_INT32_PJ == 0.1
        assert P.E_MUL_INT32_PJ == 3.1
        assert P.E_ADD_FP32_PJ == 0.9
        assert P.E_MUL_FP16_PJ == 1.1
        assert P.E_MUL_FP32_PJ == 3.7

    def test_per_mac_energy_is_mult_plus_fp32_accumulate(self):
        # int8 MAC = int8 mult (0.2) + fp32 add (0.9)
        assert P.energy_per_mac_pj("int8") == pytest.approx(1.1)
        # bf16/fp16 MAC = fp16 mult (1.1) + fp32 add (0.9)
        assert P.energy_per_mac_pj("bf16") == pytest.approx(2.0)
        assert P.energy_per_mac_pj("fp16") == pytest.approx(2.0)

    def test_unknown_precision_falls_back_to_int8(self):
        assert P.energy_per_mac_pj("mystery") == P.energy_per_mac_pj("int8")


class TestGateCounts:
    """SPEC-013 §2 — analytical array-multiplier / adder / register counts."""

    def test_multiplier_gate_formula(self):
        # n² AND + n(n-1) full-adders × 5 gates
        assert P.mult_gates(8) == 8 * 8 + 8 * 7 * 5   # 344
        assert P.add_gates(32) == 32 * 5              # 160
        assert P.reg_gates(32) == 32 * 5              # 160

    def test_mac_pe_gates_sum_active_lanes(self):
        gates = P.mac_pe_gates(["int8_matmul", "accumulate_fp32", "bfp16_matmul"])
        assert gates == P.mult_gates(8) + (P.add_gates(32) + P.reg_gates(32)) + (P.mult_gates(8) + 50)


class TestAreaScalesWithSize:
    """SPEC-013 §3 — the whole point: area ∝ PE count, not a constant."""

    CAPS = ["int8_matmul", "accumulate_fp32", "bfp16_matmul"]

    def test_area_is_pe_count_times_gates_times_cell(self):
        a = P.mac_array_area_um2(32, 32, self.CAPS)
        assert a == pytest.approx(32 * 32 * P.mac_pe_gates(self.CAPS) * P.A_GATE_UM2)

    def test_doubling_each_dim_quadruples_area(self):
        a32 = P.mac_array_area_um2(32, 32, self.CAPS)
        a64 = P.mac_array_area_um2(64, 64, self.CAPS)
        assert a64 == pytest.approx(4 * a32)

    def test_leakage_scales_like_area(self):
        p32 = P.mac_array_static_power_uw(32, 32, self.CAPS)
        p64 = P.mac_array_static_power_uw(64, 64, self.CAPS)
        assert p64 == pytest.approx(4 * p32)

    def test_more_precision_lanes_add_area(self):
        base = P.mac_array_area_um2(32, 32, ["int8_matmul", "accumulate_fp32"])
        with_fp16 = P.mac_array_area_um2(
            32, 32, ["int8_matmul", "accumulate_fp32", "fp16_matmul"]
        )
        assert with_fp16 > base

    def test_reference_node_is_stated(self):
        assert P.REFERENCE_NODE_NM == 45


class TestVauPhysical:
    """SPEC-013 §5 — VAU area ∝ lanes, energy from Horowitz FP figures."""

    CAPS = ["vector_add", "vector_mul", "vector_max", "relu"]

    def test_area_is_lanes_times_lane_gates_times_cell(self):
        a = P.vau_area_um2(16, self.CAPS)
        assert a == pytest.approx(16 * P.vau_lane_gates(self.CAPS) * P.A_GATE_UM2)

    def test_doubling_lanes_doubles_area(self):
        assert P.vau_area_um2(32, self.CAPS) == pytest.approx(2 * P.vau_area_um2(16, self.CAPS))

    def test_multiplier_lane_dominates(self):
        # An FP multiplier lane is far larger than an adder lane.
        assert P._VAU_LANE_GATES["vector_mul"] > 5 * P._VAU_LANE_GATES["vector_add"]

    def test_energy_sums_active_op_horowitz_values(self):
        assert P.vau_energy_per_elem_pj(["vector_add"]) == P.E_ADD_FP32_PJ
        assert P.vau_energy_per_elem_pj(["vector_mul"]) == P.E_MUL_FP32_PJ
        assert P.vau_energy_per_elem_pj(["relu"]) == P.E_ADD_INT32_PJ

    def test_fp_multiplier_costs_more_gates_than_fp_adder(self):
        assert P.fp_mul_gates(24) > P.fp_add_gates(24)


class TestDsbPhysical:
    """SPEC-013 §5 — DSB SRAM macro area/energy from published SRAM figures."""

    def test_sram_read_energy_scales_from_horowitz_32b(self):
        # 4 bytes = one 32-bit read = 5 pJ.
        assert P.sram_read_energy_pj(4) == pytest.approx(P.E_SRAM_RD_32B_PJ)
        assert P.sram_read_energy_pj(8) == pytest.approx(2 * P.E_SRAM_RD_32B_PJ)

    def test_macro_area_includes_peripheral_overhead(self):
        # Macro > raw cell array (decoders/sense-amps), by 1/efficiency.
        cells = P.sram_area_um2(64 * 1024)
        macro = P.sram_macro_area_um2(64 * 1024)
        assert macro == pytest.approx(cells / P.SRAM_ARRAY_EFFICIENCY)
        assert macro > cells

    def test_area_scales_with_buffer_kb(self):
        assert P.dsb_area_um2(64, True) == pytest.approx(2 * P.dsb_area_um2(32, True))

    def test_double_buffering_doubles_storage(self):
        assert P.dsb_storage_bytes(64, True) == 2 * P.dsb_storage_bytes(64, False)
        assert P.dsb_area_um2(64, True) == pytest.approx(2 * P.dsb_area_um2(64, False))

    def test_double_buffered_energy_is_read_plus_write(self):
        # double-buffer adds the write access → 2× a read-only element.
        assert P.dsb_energy_per_elem_pj(True, 1) == pytest.approx(
            2 * P.dsb_energy_per_elem_pj(False, 1)
        )

    def test_broadcast_replicates_energy(self):
        # broadcast_factor=2 → element read replicated to 2 sinks.
        assert P.dsb_energy_per_elem_pj(False, 2) == pytest.approx(
            2 * P.dsb_energy_per_elem_pj(False, 1)
        )


class TestAvpPhysical:
    """SPEC-013 §5 — AVP = FP-ALU array (∝ vector_width) + LUT SRAM (∝ entries)."""

    CAPS = ["gelu", "softmax", "layernorm"]

    def test_area_is_alu_plus_lut(self):
        alu = 16 * P.avp_lane_gates(self.CAPS) * P.A_GATE_UM2
        lut = P.sram_macro_area_um2(P.avp_lut_bytes(256))
        assert P.avp_area_um2(16, 256, self.CAPS) == pytest.approx(alu + lut)

    def test_area_grows_with_vector_width(self):
        assert P.avp_area_um2(32, 256, self.CAPS) > P.avp_area_um2(16, 256, self.CAPS)

    def test_area_grows_with_lut_entries(self):
        assert P.avp_area_um2(16, 1024, self.CAPS) > P.avp_area_um2(16, 256, self.CAPS)

    def test_energy_per_elem_is_lut_read_plus_fp_interp(self):
        one = P.avp_energy_per_elem_pj(["softmax"])
        assert one == pytest.approx(
            P.sram_read_energy_pj(P.AVP_LUT_ENTRY_BYTES) + P.E_MUL_FP32_PJ + P.E_ADD_FP32_PJ
        )
        # summed over active ops
        assert P.avp_energy_per_elem_pj(["softmax", "gelu"]) == pytest.approx(2 * one)


class TestDagcPhysical:
    """SPEC-013 §5 — DAGC unpack logic (∝ throughput) + staging RF + join FIFO."""

    CAPS = ["bfp8_unpack", "bfp16_unpack", "bfp8_bfp16_mix", "int4_reorder"]

    def test_area_scales_with_unpack_throughput(self):
        a2 = P.dagc_area_um2(2, 1, 16, self.CAPS)
        a8 = P.dagc_area_um2(8, 1, 16, self.CAPS)
        assert a8 > a2

    def test_area_grows_with_join_fifo_depth(self):
        assert P.dagc_area_um2(2, 1, 64, self.CAPS) > P.dagc_area_um2(2, 1, 16, self.CAPS)

    def test_compact_unpack_shrinks_staging(self):
        full = P.dagc_area_um2(4, 2, 16, self.CAPS)
        compact = P.dagc_area_um2(4, 2, 16, self.CAPS + ["compact_unpack"])
        assert compact < full
        assert full - compact >= 1500   # preserves the SPEC-005 §U.1 tradeoff

    def test_staging_reflects_throughput(self):
        assert P.dagc_staging_bytes(4, 2) > P.dagc_staging_bytes(2, 1)

    def test_energy_is_int_shift_grounded(self):
        assert P.dagc_energy_per_elem_pj(["bfp8_unpack"]) == pytest.approx(P.E_ADD_INT32_PJ)
        # mixed precision adds an extra align op
        assert P.dagc_energy_per_elem_pj(["bfp8_unpack", "bfp8_bfp16_mix"]) == pytest.approx(
            2 * P.E_ADD_INT32_PJ
        )


class TestCachePhysical:
    """SPEC-013 §5 — on-chip SRAM cache (L2) area/energy from the SRAM model."""

    def test_cache_area_is_sram_macro(self):
        assert P.cache_area_um2(512) == pytest.approx(P.sram_macro_area_um2(512 * 1024))

    def test_cache_density_replaces_hand_picked_800(self):
        # Physical 45nm SRAM density is ~2926 µm²/KB, not the old 800.
        density = P.cache_area_um2(1)
        assert 2500 < density < 3300

    def test_cache_area_scales_linearly(self):
        assert P.cache_area_um2(2048) == pytest.approx(4 * P.cache_area_um2(512))


class TestCamAndFifoPhysical:
    """SPEC-013 §5 — TLB CAM (MMU) and command register file (CMDQ)."""

    def test_cam_cell_is_denser_penalty_over_sram(self):
        # CAM cell carries match logic → larger than a plain SRAM bit.
        assert P.A_CAM_BIT_UM2 > P.A_SRAM_BIT_UM2

    def test_mmu_area_scales_with_tlb_entries(self):
        assert P.mmu_area_um2(256) > P.mmu_area_um2(64)
        # walker logic is a fixed floor present even at tiny TLBs
        assert P.mmu_area_um2(1) > P.logic_block_area_um2(P.TLB_WALKER_GATES) * 0.9

    def test_cmdq_area_scales_with_depth(self):
        assert P.cmdq_area_um2(256, False) == pytest.approx(4 * P.cmdq_area_um2(64, False))

    def test_cmdq_priority_adds_arbiter_logic(self):
        assert P.cmdq_area_um2(64, True) > P.cmdq_area_um2(64, False)
