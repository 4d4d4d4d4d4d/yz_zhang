"""SPEC-003 v1.1 §2.2 — DAGC 外置 use case, YAML+仿真驱动评估。

Drives:
  baseline = dagc_chain.yaml                   (DAGC on-die)
  variant  = usecase_dagc_external.yaml        (DAGC __relocate__-ed off-die)

The __relocate__ override injects a +10% latency penalty into all outgoing
connections from the relocated module, so the simulator's drain_time
reflects the off-die transport cost without any module rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate_and_run
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


@pytest.fixture(scope="module")
def report():
    base = elaborate_and_run(str(FIXTURES / "dagc_chain.yaml"), max_cycles=400)
    var = elaborate_and_run(
        str(FIXTURES / "usecase_dagc_external.yaml"), max_cycles=400
    )
    return compare(base, var)


class TestRelocateAffectsDrainTime:
    """§2.2.2 / SPEC-007 §6.3-equivalent: relocate physically delays transport."""

    def test_drain_time_increases_with_relocate(self, report):
        assert report.drain_time_delta_ps > 0, (
            f"__relocate__ should slow the sim, got Δ={report.drain_time_delta_ps:+d} ps"
        )

    def test_relocate_does_not_change_token_count(self, report):
        for key in report.baseline.tokens_delivered:
            assert report.baseline.tokens_delivered[key] == \
                   report.variant.tokens_delivered.get(key, 0), (
                f"Relocate must not drop tokens on {key}"
            )

    def test_both_runs_valid(self, report):
        assert report.both_valid


class TestRelocateAreaPolicy:
    """§2.2.2: area_penalty_pct=0 in fixture → area unchanged."""

    def test_area_unchanged_when_pct_zero(self, report):
        assert report.area_delta_um2 == pytest.approx(0.0, abs=1e-3), (
            f"area_penalty_pct=0 should leave area unchanged, "
            f"got Δ={report.area_delta_um2:+.3f}"
        )


class TestRelocateValidation:
    def test_same_die_relocate_is_rejected(self, tmp_path):
        """§2.2 schema: from_die == to_die is a no-op and must error."""
        from npu_sim.core.errors import OverrideError
        from npu_sim.evaluation import elaborate as _elaborate

        bad = tmp_path / "bad_relocate.yaml"
        bad.write_text(f"""schema_version: "1.0"
name: "bad relocate"
base: {FIXTURES / "dagc_chain.yaml"}
overrides:
  modules:
    dagc:
      __relocate__:
        from_die: 0
        to_die: 0
        latency_penalty_pct: 5
""")
        with pytest.raises(OverrideError, match="from_die equals to_die"):
            _elaborate(str(bad))


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
