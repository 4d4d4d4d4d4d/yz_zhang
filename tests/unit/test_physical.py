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
