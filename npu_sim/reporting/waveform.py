"""Per-cycle activity recorder + ASCII waveform renderer.

Captures :meth:`IModule.snapshot_state` on every cycle of a simulation
run, then renders it as a text waveform so cycle-by-cycle interaction
between modules is directly visible — answering the user contract
"能反应一拍一拍的变化,不同器件通过状态机模拟,互相交互".

Usage:
    recorder = WaveformRecorder()
    result = run_simulation(arch, max_cycles=..., per_cycle_hook=recorder)
    print(recorder.render(arch))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from npu_sim.architecture.architecture import IArchitecture


@dataclass
class WaveformRecorder:
    """Captures (cycle, module_id) → state-name on every simulator tick."""

    _trace: list[dict[str, str]] = field(default_factory=list)

    def __call__(self, cycle: int, arch: IArchitecture) -> None:
        """Hook for SimpleScheduler / run_simulation per-cycle callback."""
        row: dict[str, str] = {}
        for mid, m in arch.modules.items():
            s = m.snapshot_state()
            if not s.busy:
                row[mid] = "idle"
            elif s.current_op:
                row[mid] = s.current_op
            else:
                row[mid] = "busy"
        self._trace.append(row)

    @property
    def cycles_recorded(self) -> int:
        return len(self._trace)

    def state_at(self, cycle: int, module_id: str) -> str:
        return self._trace[cycle].get(module_id, "?")

    # ============================================================
    # Rendering
    # ============================================================

    def render(
        self,
        arch: IArchitecture,
        modules: Optional[Iterable[str]] = None,
        max_cycles: Optional[int] = None,
        condense_idle: bool = True,
    ) -> str:
        """Render a text waveform.

        Each row is a module; each column is a cycle. The cell shows '·'
        for idle, '█' for busy (any stage), or the first char of the stage
        name when stages are named. A legend is printed below.

        ``condense_idle=True`` (default) collapses long stretches of all-idle
        cycles so the output stays readable for runs of thousands of cycles.
        """
        if not self._trace:
            return "(no cycles recorded — pass per_cycle_hook=recorder to run_simulation)"

        mod_ids = list(modules) if modules else list(arch.modules.keys())
        # Drop modules that were never busy — keeps the chart focused.
        active_ids = [
            mid for mid in mod_ids
            if any(row.get(mid, "idle") != "idle" for row in self._trace)
        ]
        if not active_ids:
            active_ids = mod_ids

        n = min(max_cycles, len(self._trace)) if max_cycles else len(self._trace)

        # Identify visible cycles (skip all-idle ranges if condensing).
        if condense_idle:
            visible: list[Optional[int]] = []
            prev_all_idle = False
            for c in range(n):
                all_idle = all(self._trace[c].get(mid, "idle") == "idle" for mid in active_ids)
                if all_idle:
                    if not prev_all_idle:
                        visible.append(c)
                        visible.append(None)  # marker for "..."
                    prev_all_idle = True
                else:
                    if prev_all_idle and visible and visible[-1] is None:
                        pass  # keep the gap marker
                    visible.append(c)
                    prev_all_idle = False
        else:
            visible = list(range(n))

        # Build header (cycle markers every 10).
        label_w = max(len(m) for m in active_ids) + 2
        header_chars = []
        tick_chars = []
        for v in visible:
            if v is None:
                header_chars.append("…")
                tick_chars.append("…")
            else:
                tick_chars.append("|" if v % 10 == 0 else " ")
                header_chars.append(str(v // 10 % 10) if v % 10 == 0 else " ")

        lines: list[str] = []
        lines.append(" " * label_w + "".join(header_chars))
        lines.append(" " * label_w + "".join(tick_chars))

        # Stage glyph map — unique single-char per distinct stage name.
        stage_glyphs: dict[str, str] = {}
        used_glyphs: set[str] = {"·", "…", " ", "|"}
        # Try first-char (uppercase), then digits, then lowercase letters.
        _candidate_pool = (
            [c.upper() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
            + list("0123456789")
            + [c for c in "abcdefghijklmnopqrstuvwxyz"]
        )

        def glyph_for(state: str) -> str:
            if state == "idle":
                return "·"
            if state in stage_glyphs:
                return stage_glyphs[state]
            preferred = state[0].upper() if state[:1].isalpha() else None
            if preferred and preferred not in used_glyphs:
                g = preferred
            else:
                g = next((c for c in _candidate_pool if c not in used_glyphs), "█")
            stage_glyphs[state] = g
            used_glyphs.add(g)
            return g

        for mid in active_ids:
            cells = []
            for v in visible:
                if v is None:
                    cells.append("…")
                else:
                    cells.append(glyph_for(self._trace[v].get(mid, "idle")))
            lines.append(f"{mid:<{label_w}}" + "".join(cells))

        # Legend.
        lines.append("")
        lines.append("Legend: · idle, … condensed run of all-idle cycles")
        for state, g in sorted(stage_glyphs.items()):
            lines.append(f"        {g}  {state}")
        return "\n".join(lines)
