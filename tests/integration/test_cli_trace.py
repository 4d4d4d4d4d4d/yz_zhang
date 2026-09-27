"""CLI `trace` subcommand — renders a cycle-by-cycle waveform of a
SPEC-005 + SPEC-007 architecture from a single YAML.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from npu_sim.cli import main as cli_main


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


class TestCLITrace:
    def test_trace_renders_npu_pipeline_waveform(self):
        buf = io.StringIO()
        rc = cli_main(
            [
                "trace",
                str(FIXTURES / "usecase_npu_full_baseline.yaml"),
                "--max-cycles", "600",
                "--show-cycles", "200",
            ],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        # All SPEC-005 + SPEC-007 module ids should appear in the chart.
        for mid in ("prod", "dagc", "dsb", "mac", "vau", "avp", "cons"):
            assert mid in s, f"module {mid!r} missing from trace output"
        # Stage glyphs from each module should be in the legend.
        for stage in ("unpack_bfp", "stage_tile", "writeback_psum",
                      "vector_op", "lut_lookup"):
            assert stage in s, f"stage {stage!r} not in trace legend"

    def test_trace_renders_mcu_ogu_handshake(self):
        buf = io.StringIO()
        rc = cli_main(
            [
                "trace",
                str(FIXTURES / "usecase_mcu_with_ogu.yaml"),
                "--max-cycles", "300",
                "--show-cycles", "200",
            ],
            out=buf,
        )
        assert rc == 0
        s = buf.getvalue()
        # MCU + OGU stages must show parallel execution.
        for stage in ("op_config_local", "buffsize", "bd_gen"):
            assert stage in s, f"stage {stage!r} missing from trace legend"


class TestCLITraceErrors:
    def test_trace_bad_path_returns_error_code(self):
        buf = io.StringIO()
        with pytest.raises(SystemExit):
            cli_main(["trace", "/nonexistent.yaml"], out=buf)
