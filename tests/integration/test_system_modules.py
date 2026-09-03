"""SPEC-010 Tier 3 — PMU / SYNC evaluations.

YAML+sim compare for system infrastructure modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from npu_sim.evaluation import compare, elaborate, elaborate_and_run
import npu_sim.modules  # noqa: F401
from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


def _cmp(b, v, cycles=3000):
    return compare(
        elaborate_and_run(str(FIXTURES / b), max_cycles=cycles),
        elaborate_and_run(str(FIXTURES / v), max_cycles=cycles),
    )


class TestPMU:
    def test_more_counters_grows_area(self):
        r = _cmp("usecase_pmu_small.yaml", "usecase_pmu_wide.yaml")
        # SPEC-013: n_counters 2 → 8: +6 counters × (48-bit reg + incrementer)
        assert r.area_delta_um2 == pytest.approx(2_304, abs=10)

    def test_pmu_does_not_drag_pipeline(self):
        """PMU is a passive observer; main pipeline drain shouldn't change."""
        r = _cmp("usecase_pmu_small.yaml", "usecase_pmu_wide.yaml")
        assert r.drain_time_delta_ps == 0


class TestSYNC:
    def test_more_participants_grows_register_area(self):
        r = _cmp("usecase_sync_2p.yaml", "usecase_sync_8p.yaml")
        # n_participants 2 → 8: +6 × 1500 = +9_000
        assert r.area_delta_um2 == pytest.approx(9_000, abs=100)

    def test_sync_registered_and_has_arrive_release_ports(self):
        from npu_sim.core.module_registry import ModuleRegistry
        assert "SYNC" in ModuleRegistry.list_modules()
        a = elaborate(str(FIXTURES / "usecase_sync_2p.yaml"))
        assert {p.name for p in type(a.modules["sync"]).port_specs()} == \
               {"arrive_in", "release_out"}


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
