"""Data-movement energy model — SPEC-014.

Verifies per-op operand traffic (§1), the SRAM-vs-DRAM spill rule (§2), the
compute+movement+static decomposition (§3/T.3), and the headline result
(T.4): with data movement counted, total energy DIFFERENTIATES by design —
a small on-chip buffer spills weights to DRAM and costs more — fixing the
"energy is design-invariant" artifact of the compute-only model.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from npu_sim.evaluation import (
    analyze_energy,
    data_movement_energy_pj,
    elaborate,
    onchip_capacity_bytes,
    op_traffic_bytes,
)
from npu_sim.evaluation.trace_ops import ops_from_list
import npu_sim.modules  # noqa: F401


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
BASE = os.path.abspath(str(FIXTURES / "usecase_chip_trace_driven.yaml"))


def _design(dsb_kb: int):
    ov = {"schema_version": "1.0", "name": "d", "base": BASE,
          "overrides": {"modules": {"dsb": {"config": {"buffer_kb": dsb_kb}}}}}
    p = Path(tempfile.mkdtemp()) / "d.yaml"
    p.write_text(yaml.safe_dump(ov), encoding="utf-8")
    return elaborate(str(p))


class TestOpTraffic:
    """SPEC-014 §T.1 — operand-byte formulas."""

    def test_matmul_traffic(self):
        op = ops_from_list([{"op_type": "matmul", "m": 128, "k": 256, "n": 1024,
                             "precision": "int8"}])[0]
        act, weight, out = op_traffic_bytes(op)
        assert act == 128 * 256 * 1        # M·K·p (int8)
        assert weight == 256 * 1024 * 1    # K·N·p
        assert out == 128 * 1024 * 4       # M·N·4 (FP32 psum)

    def test_precision_scales_bytes(self):
        i8 = ops_from_list([{"op_type": "matmul", "m": 8, "k": 8, "n": 8, "precision": "int8"}])[0]
        f16 = ops_from_list([{"op_type": "matmul", "m": 8, "k": 8, "n": 8, "precision": "bf16"}])[0]
        assert op_traffic_bytes(f16)[1] == 2 * op_traffic_bytes(i8)[1]

    def test_elementwise_traffic(self):
        op = ops_from_list([{"op_type": "gelu", "n_elements": 100}])[0]
        act, weight, out = op_traffic_bytes(op)
        assert weight == 0 and act == out == 100 * 4  # fp32 default


class TestSpillRule:
    """SPEC-014 §T.2 — weights fitting on-chip read at SRAM rate, else DRAM."""

    def test_dram_spill_costs_far_more(self):
        op = ops_from_list([{"op_type": "matmul", "m": 128, "k": 256, "n": 1024,
                             "precision": "int8"}])
        big = data_movement_energy_pj(op, _design(512))   # fits
        small = data_movement_energy_pj(op, _design(32))  # spills
        assert not big.any_weight_spilled
        assert small.any_weight_spilled
        assert small.total_pj > 5 * big.total_pj

    def test_capacity_reflects_buffer(self):
        assert onchip_capacity_bytes(_design(128)) == 128 * 1024


class TestEnergyDecomposition:
    """SPEC-014 §T.3 — total = compute + movement + static; movement counted."""

    def test_total_includes_movement(self):
        ops = ops_from_list([{"op_type": "matmul", "m": 128, "k": 256, "n": 1024,
                              "precision": "int8"}])
        r = analyze_energy(ops, _design(32))
        assert r.movement_pj > 0
        assert r.total_pj == pytest.approx(r.dynamic_pj + r.movement_pj + r.static_pj)


class TestEnergyDifferentiatesByDesign:
    """SPEC-014 §T.4 — the headline: buffer sizing now moves total energy."""

    def test_small_buffer_costs_more_energy(self):
        ops = ops_from_list([
            {"op_type": "matmul", "m": 128, "k": 256, "n": 1024, "precision": "int8"},
            {"op_type": "matmul", "m": 128, "k": 1024, "n": 256, "precision": "int8"},
        ])
        big = analyze_energy(ops, _design(512))
        small = analyze_energy(ops, _design(32))
        assert small.dynamic_pj == pytest.approx(big.dynamic_pj)   # compute invariant
        assert small.total_pj > big.total_pj                       # total is NOT
        assert small.weights_spilled and not big.weights_spilled
