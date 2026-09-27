"""Per-module knob audit: each headline SPEC-005 timing knob must produce an
observable performance Δ via compare().

For each module's chain fixture (Producer→Module→Consumer) we run the
baseline against a variant in SPEC-003 §6 override form that halves one
config knob, and assert the comparator detects the regression in
drain_time / stall (the spec-meaningful latency signals after the §7
finding).

AVP is already covered end-to-end by test_npu_pipeline.py::TestPipelineRegression.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401  registers all module types


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"

# (label, baseline_fixture, variant_fixture)
_KNOB_CASES = [
    ("dagc.bfp8_unpack_throughput", "dagc_chain.yaml", "dagc_chain_slow_bfp8.yaml"),
    ("dsb.read_throughput",         "dsb_chain.yaml",  "dsb_chain_slow_read.yaml"),
    ("mac.array_size",              "mac_chain.yaml",  "mac_chain_smaller_array.yaml"),
    ("vau.lanes",                   "vau_chain.yaml",  "vau_chain_fewer_lanes.yaml"),
]


@pytest.mark.parametrize("label,base_yaml,variant_yaml", _KNOB_CASES,
                         ids=[c[0] for c in _KNOB_CASES])
def test_module_knob_produces_observable_delta(label, base_yaml, variant_yaml):
    """SPEC-005 §1.6 (estimate_latency knobs) → SPEC-003 §7 R7 (compare archetype).

    Halving a module's headline throughput knob must produce an observable
    regression in drain_time and/or stall, with both runs remaining valid.
    """
    baseline = elaborate_and_run(str(FIXTURES / base_yaml), max_cycles=4000)
    variant = elaborate_and_run(str(FIXTURES / variant_yaml), max_cycles=4000)
    report = compare(baseline, variant)
    assert report.both_valid, label
    assert (
        report.drain_time_delta_ps > 0 or report.stall_delta_ps > 0
    ), f"{label}: no observable regression (drain_Δ={report.drain_time_delta_ps}, stall_Δ={report.stall_delta_ps})"
