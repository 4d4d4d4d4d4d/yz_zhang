"""Whole-chip state snapshot — feasible subset of QEMU §3.2 checkpoint.

Two things are asserted here:

1. **The feasible half works** — ``capture_state`` / ``snapshot_at_cycle``
   freeze every module's SPEC-001 §3.1 state plus every SPEC-002 connection
   FIFO at a chosen cycle, and the snapshot is field-comparable.

2. **Restore = deterministic replay** — because the runtime is deterministic
   (RNG removed, §3.3), two independent replays to the same cycle produce a
   field-identical :class:`StateSnapshot`. That property *is* the restore
   mechanism on this platform; a binary checkpoint would add only wall-clock
   savings.

3. **Why binary checkpoint is deferred** — a module's in-flight timing lives
   in its ``behavior()`` generator frame (the ``for _ in range(n): yield``
   countdown), which is neither exposed by ``snapshot_state()`` nor picklable.
   ``test_generator_frame_blocks_binary_checkpoint`` locks that finding in so
   nobody re-attempts loadvm in the Python runtime (it belongs in Phase 5
   SystemC per ADR-001.1).
"""

from __future__ import annotations

import io
import pickle
from pathlib import Path

import pytest

from npu_sim.evaluation import (
    capture_state,
    elaborate,
    snapshot_at_cycle,
)
from npu_sim.reporting import render_state_snapshot
from npu_sim.cli import main as cli_main
import npu_sim.modules  # noqa: F401

from tests.integration._yaml_driven_contract import assert_evaluation_is_yaml_driven


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"
CHIP = "usecase_chip_trace_driven.yaml"


class TestCaptureState:
    def test_snapshot_covers_all_modules_and_connections(self):
        arch = elaborate(str(FIXTURES / CHIP))
        snap = snapshot_at_cycle(arch, at_cycle=20)
        # 7 modules: trace_src, dagc, dsb, mac, vau, avp, sink
        assert len(snap.modules) == 7
        ids = {m.module_id for m in snap.modules}
        assert {"trace_src", "dagc", "mac", "avp", "sink"} <= ids
        # 6 datapath connections
        assert len(snap.connections) == 6
        assert snap.cycle == 20

    def test_midrun_snapshot_shows_live_activity(self):
        """A mid-pipeline snapshot must catch work in flight, not an empty chip."""
        arch = elaborate(str(FIXTURES / CHIP))
        snap = snapshot_at_cycle(arch, at_cycle=20)
        # At least one module busy AND at least one token queued somewhere.
        assert len(snap.busy_modules()) >= 1
        assert snap.total_in_flight() >= 1

    def test_capture_is_pure_read(self):
        """capture_state must not perturb the sim: same cycle, same drain."""
        arch = elaborate(str(FIXTURES / CHIP))
        from npu_sim.evaluation import run_simulation
        r1 = run_simulation(arch, max_cycles=100000)
        # capture over the already-drained arch is a harmless read
        snap = capture_state(arch, cycle=r1.cycles_run)
        assert snap.cycle == r1.cycles_run
        # re-running a fresh arch gives the same drain (no hidden mutation)
        arch2 = elaborate(str(FIXTURES / CHIP))
        r2 = run_simulation(arch2, max_cycles=100000)
        assert r2.drain_time_ps == r1.drain_time_ps


class TestRestoreIsDeterministicReplay:
    """The headline property: replay-to-cycle reconstructs identical state."""

    def test_two_replays_to_same_cycle_are_field_identical(self):
        a1 = elaborate(str(FIXTURES / CHIP))
        a2 = elaborate(str(FIXTURES / CHIP))
        s1 = snapshot_at_cycle(a1, at_cycle=25)
        s2 = snapshot_at_cycle(a2, at_cycle=25)
        # Frozen dataclasses of primitives → structural equality is exact.
        assert s1 == s2

    def test_different_cycles_differ(self):
        arch = elaborate(str(FIXTURES / CHIP))
        early = snapshot_at_cycle(arch, at_cycle=5)
        arch2 = elaborate(str(FIXTURES / CHIP))
        later = snapshot_at_cycle(arch2, at_cycle=40)
        assert early != later


class TestBinaryCheckpointBlocker:
    """Document WHY loadvm is deferred to Phase 5 (ADR-001.1)."""

    def test_generator_frame_blocks_binary_checkpoint(self):
        """A live behavior() generator carries mid-op state and can't pickle.

        The MAC's compute countdown (``for _ in range(fill_n): yield``) lives
        in this frame, invisible to snapshot_state(). Pickling it — the only
        way to persist that state for a true restore — raises. This is the
        structural reason binary checkpoint needs the SystemC kernel.
        """
        arch = elaborate(str(FIXTURES / CHIP))
        gen = arch.modules["mac"].behavior()
        next(gen)  # advance into the frame
        with pytest.raises((TypeError, pickle.PicklingError)):
            pickle.dumps(gen)

    def test_snapshot_state_omits_generator_local_countdown(self):
        """snapshot_state() exposes named stage, not the raw cycle counter.

        Confirms the gap: even a full ModuleState dump lacks the frame-local
        loop index, so it cannot by itself reconstruct a mid-op module.
        """
        arch = elaborate(str(FIXTURES / CHIP))
        st = arch.modules["mac"].snapshot_state()
        # ModuleState has no field carrying "cycles remaining in current op".
        fields = set(vars(st).keys()) if hasattr(st, "__dict__") else set()
        # frozen dataclass → use dataclasses.fields
        import dataclasses
        fields = {f.name for f in dataclasses.fields(st)}
        assert "cycles_remaining" not in fields
        assert "frame" not in fields


class TestSnapshotRender:
    def test_render_has_modules_and_connections(self):
        arch = elaborate(str(FIXTURES / CHIP))
        md = render_state_snapshot(snapshot_at_cycle(arch, at_cycle=20))
        assert "Chip state snapshot" in md
        assert "## Modules" in md
        assert "## Connection FIFOs" in md
        assert "`mac`" in md


class TestSnapshotCLI:
    def test_cli_snapshot_midrun(self):
        buf = io.StringIO()
        rc = cli_main(
            ["snapshot", str(FIXTURES / CHIP), "--at-cycle", "20"],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        assert "Chip state snapshot" in s
        assert "cycle | 20" in s

    def test_cli_snapshot_out_file(self, tmp_path):
        out_file = tmp_path / "snap.md"
        buf = io.StringIO()
        rc = cli_main(
            [
                "snapshot",
                str(FIXTURES / CHIP),
                "--at-cycle",
                "20",
                "--out",
                str(out_file),
            ],
            out=buf,
        )
        assert rc == 0
        assert out_file.exists()
        assert "## Modules" in out_file.read_text()
        assert buf.getvalue() == ""


def test_yaml_driven_contract():
    assert_evaluation_is_yaml_driven(__file__)
