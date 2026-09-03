"""Whole-chip snapshot diff — internal A/B divergence at a cycle.

`compare` diffs only aggregate metrics; `diff_snapshots` diffs the internal
state (module stage/FIFO, connection occupancy) so a same-topology variant
pair can be inspected for exactly where it diverges. Builds on the
deterministic snapshot (test_state_snapshot.py): both sides replay to the
same cycle, so the diff is itself deterministic.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.evaluation import diff_snapshots, elaborate, snapshot_at_cycle
from npu_sim.reporting import render_snapshot_diff
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
MAC = "mac_chain.yaml"
MAC_SMALL = "mac_chain_smaller_array.yaml"
CHIP = "usecase_chip_trace_driven.yaml"


def _snap(name: str, at_cycle: int):
    return snapshot_at_cycle(elaborate(str(FIXTURES / name)), at_cycle=at_cycle)


class TestDiffSameArchIsIdentical:
    def test_arch_against_itself_is_identical(self):
        d = diff_snapshots(_snap(MAC, 15), _snap(MAC, 15))
        assert d.identical
        assert d.module_diffs == ()
        assert d.connection_diffs == ()
        assert d.only_in_a == () and d.only_in_b == ()


class TestDiffVariantPair:
    """Same topology, different MAC array size → internal divergence."""

    def test_topology_matches_but_state_differs(self):
        d = diff_snapshots(_snap(MAC, 15), _snap(MAC_SMALL, 15))
        # identical module set → nothing only-in-one-side
        assert d.only_in_a == () and d.only_in_b == ()
        # but internal state diverges
        assert not d.identical
        assert len(d.module_diffs) >= 1
        assert len(d.connection_diffs) >= 1

    def test_diverging_connection_is_the_mac_input(self):
        d = diff_snapshots(_snap(MAC, 15), _snap(MAC_SMALL, 15))
        conn_entities = {fd.entity for fd in d.connection_diffs}
        # smaller array is slower (more compute cycles) → input FIFO backs up
        assert any("prod.out→mac.in_act" == e for e in conn_entities)
        infl = [fd for fd in d.connection_diffs
                if fd.entity == "prod.out→mac.in_act" and fd.field == "in_flight"]
        assert infl and infl[0].value_a != infl[0].value_b

    def test_diff_is_deterministic(self):
        d1 = diff_snapshots(_snap(MAC, 15), _snap(MAC_SMALL, 15))
        d2 = diff_snapshots(_snap(MAC, 15), _snap(MAC_SMALL, 15))
        assert d1 == d2


class TestDiffDifferentTopology:
    def test_only_in_side_reports_missing_modules(self):
        d = diff_snapshots(_snap(MAC, 10), _snap(CHIP, 10))
        # MAC chain: prod/cons; chip: trace_src/dagc/dsb/vau/avp/sink — uniques both sides
        assert "prod" in d.only_in_a and "cons" in d.only_in_a
        assert "trace_src" in d.only_in_b and "sink" in d.only_in_b
        assert not d.identical


class TestRenderDiff:
    def test_render_shows_differences(self):
        d = diff_snapshots(_snap(MAC, 15), _snap(MAC_SMALL, 15))
        md = render_snapshot_diff(d)
        assert "Chip state diff" in md
        assert "Module state differences" in md
        assert "Connection FIFO differences" in md

    def test_render_identical(self):
        d = diff_snapshots(_snap(MAC, 15), _snap(MAC, 15))
        md = render_snapshot_diff(d)
        assert "identical" in md.lower()


class TestSnapshotDiffCLI:
    def test_cli_returns_1_when_differ(self):
        buf = io.StringIO()
        rc = cli_main(
            ["snapshot-diff", str(FIXTURES / MAC), str(FIXTURES / MAC_SMALL),
             "--at-cycle", "15"],
            out=buf,
        )
        assert rc == 1  # differs
        assert "Module state differences" in buf.getvalue()

    def test_cli_returns_0_when_identical(self):
        buf = io.StringIO()
        rc = cli_main(
            ["snapshot-diff", str(FIXTURES / MAC), str(FIXTURES / MAC),
             "--at-cycle", "15"],
            out=buf,
        )
        assert rc == 0
        assert "identical" in buf.getvalue().lower()


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
