"""CLI tests. Invoke handlers in-process where possible; one subprocess
test exercises the `python -m npu_sim` shim end-to-end.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from npu_sim.cli import main


FIXTURES = Path(__file__).parent.parent / "fixtures" / "architectures"


# ============================================================
# list-modules
# ============================================================


class TestListModules:

    def test_lists_known_modules(self):
        buf = io.StringIO()
        rc = main(["list-modules"], out=buf)
        assert rc == 0
        text = buf.getvalue()
        # Probe modules registered at import time.
        for expected in ("Dummy", "Producer", "Consumer", "Passthrough", "Merger"):
            assert expected in text
        # Numerical model section present.
        assert "INumericalModel" in text


# ============================================================
# simulate
# ============================================================


class TestSimulate:

    def test_baseline_simulate_returns_0_and_renders_markdown(self):
        buf = io.StringIO()
        rc = main(
            ["simulate", str(FIXTURES / "usecase_baseline.yaml"),
             "--max-cycles", "500"],
            out=buf,
        )
        assert rc == 0
        text = buf.getvalue()
        assert "# Simulation Report:" in text
        assert "✅ VALID" in text

    def test_invalid_run_returns_1(self):
        # probe_never_consume hits both INV-2 and INV-3.
        buf = io.StringIO()
        rc = main(
            ["simulate", str(FIXTURES / "probe_never_consume.yaml"),
             "--max-cycles", "30"],
            out=buf,
        )
        assert rc == 1
        text = buf.getvalue()
        assert "INVALID" in text

    def test_writes_to_out_file(self, tmp_path):
        out_path = tmp_path / "report.md"
        rc = main(
            ["simulate", str(FIXTURES / "usecase_baseline.yaml"),
             "--max-cycles", "500",
             "--out", str(out_path)],
        )
        assert rc == 0
        text = out_path.read_text(encoding="utf-8")
        assert "# Simulation Report:" in text

    def test_missing_dsl_exits_2(self):
        with pytest.raises(SystemExit) as excinfo:
            main(["simulate", "/does/not/exist.yaml"])
        assert excinfo.value.code == 2


# ============================================================
# compare
# ============================================================


class TestCompare:

    def test_baseline_vs_variant_returns_0(self):
        buf = io.StringIO()
        rc = main(
            ["compare",
             str(FIXTURES / "usecase_baseline.yaml"),
             str(FIXTURES / "usecase_variant_slow_cons.yaml"),
             "--max-cycles", "500"],
            out=buf,
        )
        assert rc == 0
        text = buf.getvalue()
        assert "# Comparison:" in text
        assert "✅ VALID" in text
        assert "CHANGED" in text

    def test_writes_to_out_file(self, tmp_path):
        out_path = tmp_path / "compare.md"
        rc = main(
            ["compare",
             str(FIXTURES / "usecase_baseline.yaml"),
             str(FIXTURES / "usecase_variant_slow_cons.yaml"),
             "--max-cycles", "500",
             "--out", str(out_path)],
        )
        assert rc == 0
        text = out_path.read_text(encoding="utf-8")
        assert "# Comparison:" in text


# ============================================================
# subprocess shim (one round-trip via `python -m npu_sim`)
# ============================================================


class TestModuleShim:

    def test_python_dash_m_dispatch(self, tmp_path):
        """Smoke-test the `python -m npu_sim` entrypoint."""
        proc = subprocess.run(
            [
                sys.executable, "-m", "npu_sim", "list-modules",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert "Producer" in proc.stdout
        assert "Dummy" in proc.stdout
