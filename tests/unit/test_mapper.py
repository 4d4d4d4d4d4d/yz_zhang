"""Conformance tests for the RuleBasedMapper. Reference: SPEC-006 §7."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from npu_sim.architecture.architecture import (
    Architecture,
    ElaboratedConnection,
    ElaboratedTopology,
)
from npu_sim.core.errors import NoMappingError
from npu_sim.interfaces.module import IModule
from npu_sim.interfaces.operation import Precision, PrecisionKind, StaticOperation
from npu_sim.mapping import MappingPlan, RuleBasedMapper
from npu_sim.modules.avp import AVP
from npu_sim.modules.mac import MAC
from npu_sim.modules.vau import VAU


# ============================================================
# Fixtures: a minimal IArchitecture wrapping a configured module set
# ============================================================


def _arch(modules: dict[str, IModule]) -> Architecture:
    return Architecture(
        _name="mapper-test",
        _metadata={},
        _modules=modules,
        _connections=[],
        _clocks={},
        _topology=None,
        _mapping_hints={},
        _warnings=[],
    )


def _mac(rows=32, cols=32) -> MAC:
    m = MAC()
    m.configure({"array_rows": rows, "array_cols": cols, "support_bfp16": True})
    return m


def _vau(lanes=16) -> VAU:
    v = VAU()
    v.configure({"lanes": lanes})
    return v


def _avp(vw=16) -> AVP:
    a = AVP()
    a.configure({"vector_width": vw})
    return a


def _op(op_type: str, caps: tuple[str, ...], n_elements: int = 64,
        kind: PrecisionKind = PrecisionKind.INT8, **shape) -> StaticOperation:
    info = (("n_elements", n_elements),) + tuple(shape.items())
    return StaticOperation(
        _op_type=op_type,
        _required_capabilities=caps,
        _shape_info=info,
        _precision=Precision(kind=kind),
    )


# ============================================================
# §7.1 interface contract: pure, doesn't mutate
# ============================================================


class TestMapperInterface:

    def test_map_is_deterministic(self):
        arch = _arch({"mac": _mac(), "vau": _vau()})
        ops = [_op("matmul", ("int8_matmul",), m=8, k=8, n=8)]
        m = RuleBasedMapper()
        p1 = m.map(ops, arch)
        p2 = m.map(ops, arch)
        assert p1 == p2

    def test_map_does_not_mutate_architecture(self):
        arch = _arch({"mac": _mac()})
        ids_before = list(arch.modules.keys())
        RuleBasedMapper().map([_op("matmul", ("int8_matmul",))], arch)
        assert list(arch.modules.keys()) == ids_before

    def test_empty_ops_yields_empty_plan(self):
        plan = RuleBasedMapper().map([], _arch({"mac": _mac()}))
        assert plan.decisions == ()
        assert plan.total_typical_cycles == 0
        assert plan.total_dynamic_pj == 0.0


# ============================================================
# §7.2 candidate filtering + unmapped behavior
# ============================================================


class TestCandidateFiltering:

    def test_only_modules_that_can_execute_are_candidates(self):
        arch = _arch({"mac": _mac(), "avp": _avp()})
        # gelu requires AVP capability; MAC cannot run it.
        plan = RuleBasedMapper().map([_op("gelu", ("gelu",))], arch)
        assert plan.decisions[0].module_id == "avp"
        assert "mac" not in plan.decisions[0].alternatives

    def test_no_candidate_raises_in_strict_mode(self):
        arch = _arch({"vau": _vau()})
        # gelu requires AVP capability; VAU cannot run it.
        with pytest.raises(NoMappingError):
            RuleBasedMapper().map([_op("gelu", ("gelu",))], arch)

    def test_no_candidate_records_unmapped_in_lenient_mode(self):
        arch = _arch({"vau": _vau()})
        plan = RuleBasedMapper(strict=False).map(
            [_op("relu", ("relu",)), _op("gelu", ("gelu",))], arch
        )
        # relu maps to VAU; gelu has no candidate -> unmapped.
        assert plan.unmapped == (1,)
        assert len(plan.decisions) == 1
        assert plan.decisions[0].module_id == "vau"


# ============================================================
# §7.3 sort & tie-break determinism
# ============================================================


class TestSortingAndTieBreak:

    def test_lower_typical_cycles_wins(self):
        # Two MACs with different array sizes. At a workload large enough that
        # compute dominates fill, the bigger array wins (more PEs in parallel).
        arch = _arch({"mac_small": _mac(rows=8, cols=8), "mac_big": _mac(rows=64, cols=64)})
        plan = RuleBasedMapper().map(
            [_op("matmul", ("int8_matmul",), m=32, k=32, n=32)], arch
        )
        assert plan.decisions[0].module_id == "mac_big"
        assert plan.decisions[0].alternatives == ("mac_small",)

    def test_tie_break_is_lexicographic_module_id(self):
        # Two identically-configured MACs → identical latency & energy → tie
        # broken by module_id ascending.
        arch = _arch({"mac_b": _mac(), "mac_a": _mac()})  # dict order: b, a
        plan = RuleBasedMapper().map(
            [_op("matmul", ("int8_matmul",), m=8, k=8, n=8)], arch
        )
        assert plan.decisions[0].module_id == "mac_a"
        assert plan.decisions[0].alternatives == ("mac_b",)

    def test_result_independent_of_dict_insertion_order(self):
        ops = [_op("matmul", ("int8_matmul",), m=8, k=8, n=8)]
        plan_ab = RuleBasedMapper().map(ops, _arch({"mac_a": _mac(), "mac_b": _mac()}))
        plan_ba = RuleBasedMapper().map(ops, _arch({"mac_b": _mac(), "mac_a": _mac()}))
        assert plan_ab.decisions[0].module_id == plan_ba.decisions[0].module_id
        assert plan_ab.decisions[0].alternatives == plan_ba.decisions[0].alternatives


# ============================================================
# §7.4 alternatives completeness
# ============================================================


class TestAlternatives:

    def test_chosen_module_not_in_alternatives(self):
        arch = _arch({"mac_a": _mac(), "mac_b": _mac()})
        plan = RuleBasedMapper().map(
            [_op("matmul", ("int8_matmul",), m=8, k=8, n=8)], arch
        )
        d = plan.decisions[0]
        assert d.module_id not in d.alternatives

    def test_alternatives_ordering_matches_rank(self):
        # Three MACs of decreasing speed → alternatives sorted slowest-last.
        arch = _arch({
            "mac_fast": _mac(rows=64, cols=64),
            "mac_mid":  _mac(rows=32, cols=32),
            "mac_slow": _mac(rows=8,  cols=8),
        })
        plan = RuleBasedMapper().map(
            [_op("matmul", ("int8_matmul",), m=64, k=64, n=64)], arch
        )
        d = plan.decisions[0]
        assert d.module_id == "mac_fast"
        assert d.alternatives == ("mac_mid", "mac_slow")


# ============================================================
# §7.5 aggregate metrics
# ============================================================


class TestAggregate:

    def test_total_cycles_and_pj_equal_sum_of_decisions(self):
        arch = _arch({"mac": _mac(), "vau": _vau(), "avp": _avp()})
        ops = [
            _op("matmul", ("int8_matmul",), m=8, k=8, n=8),
            _op("relu", ("relu",)),
            _op("gelu", ("gelu",)),
        ]
        plan = RuleBasedMapper().map(ops, arch)
        assert plan.total_typical_cycles == sum(
            d.latency.typical_cycles for d in plan.decisions
        )
        assert plan.total_dynamic_pj == pytest.approx(
            sum(d.energy.dynamic_pj for d in plan.decisions)
        )


# ============================================================
# §7.6 end-to-end with real Phase 2 modules
# ============================================================


class TestEndToEndOnRealModules:

    def test_matmul_relu_gelu_route_to_expected_modules(self):
        arch = _arch({"mac": _mac(), "vau": _vau(), "avp": _avp()})
        ops = [
            _op("matmul", ("int8_matmul",), m=16, k=16, n=16),
            _op("relu", ("relu",)),
            _op("gelu", ("gelu",)),
        ]
        plan = RuleBasedMapper().map(ops, arch)
        routing = {d.op_type: d.module_id for d in plan.decisions}
        assert routing == {"matmul": "mac", "relu": "vau", "gelu": "avp"}
        assert plan.summary_text.startswith("MappingPlan:")
        assert "total:" in plan.summary_text
