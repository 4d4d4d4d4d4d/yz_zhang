"""Command-line interface: elaborate / simulate / compare architectures.

Subcommands:

    list-modules                List registered IModule + INumericalModel types.
    simulate <dsl>              Elaborate + run; print a SimulationResult report
                                as Markdown to stdout (or --out file).
    compare <baseline> <variant>
                                Run both; print a ComparisonReport.
    trace <dsl>                 Render an ASCII cycle-by-cycle waveform.
    estimate <arch> <ops>       Map an operator trace onto an architecture
                                (SPEC-006 static Mapper estimate).
    reconcile <arch> <ops>      Join the static Mapper estimate against the
                                simulated measured drain (SPEC-006 §8
                                estimate-vs-measured reconciliation).

Designed for the SPEC-003 §7 R7 workflow: researcher edits a YAML, runs
`python -m npu_sim compare base.yaml variant.yaml`, pastes the output into
a PR / email.

Exit codes:
    0   success
    1   simulation produced an INVALID invariant report
    2   elaboration / DSL error
    3   unknown subcommand / argument error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence, TextIO

import npu_sim.modules  # noqa: F401  side-effect: registers all probe modules
from npu_sim.core.errors import NpuSimError
from npu_sim.core.module_registry import ModuleRegistry
from npu_sim.core.numerical_registry import NumericalModelRegistry
from npu_sim.evaluation import compare, elaborate_and_run
from npu_sim.reporting import (
    render_comparison_report,
    render_simulation_report,
)


# ============================================================
# Subcommand handlers
# ============================================================


def _cmd_list_modules(args: argparse.Namespace, out: TextIO) -> int:
    out.write("Registered IModule types:\n")
    for name in ModuleRegistry.list_modules():
        out.write(f"  - {name}\n")
    out.write("\nRegistered INumericalModel types:\n")
    seen: dict[str, list[str]] = {}
    for (module_type, fidelity) in NumericalModelRegistry._registry:
        seen.setdefault(module_type, []).append(fidelity)
    if not seen:
        out.write("  (none)\n")
    else:
        for module_type in sorted(seen):
            fids = sorted(seen[module_type])
            out.write(f"  - {module_type}: {', '.join(fids)}\n")
    return 0


def _cmd_simulate(args: argparse.Namespace, out: TextIO) -> int:
    dsl_path = _require_path(args.dsl)
    try:
        result = elaborate_and_run(str(dsl_path), max_cycles=args.max_cycles)
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    md = render_simulation_report(result)
    _write_output(md, args.out, out)
    return 0 if result.invariant_report.overall_valid else 1


def _cmd_compare(args: argparse.Namespace, out: TextIO) -> int:
    baseline_path = _require_path(args.baseline)
    variant_path = _require_path(args.variant)
    try:
        baseline = elaborate_and_run(
            str(baseline_path), max_cycles=args.max_cycles
        )
        variant = elaborate_and_run(
            str(variant_path), max_cycles=args.max_cycles
        )
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    report = compare(baseline, variant)
    md = render_comparison_report(report)
    _write_output(md, args.out, out)
    return 0 if report.both_valid else 1


def _cmd_trace(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import elaborate
    from npu_sim.evaluation.runner import run_simulation
    from npu_sim.reporting.waveform import WaveformRecorder

    dsl_path = _require_path(args.dsl)
    try:
        arch = elaborate(str(dsl_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    recorder = WaveformRecorder()
    run_simulation(arch, max_cycles=args.max_cycles, per_cycle_hook=recorder)
    rendered = recorder.render(
        arch,
        max_cycles=args.show_cycles,
        condense_idle=not args.no_condense,
    )
    _write_output(rendered, args.out, out)
    return 0


def _cmd_estimate(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import elaborate, estimate_plan
    from npu_sim.evaluation.trace_ops import load_ops
    from npu_sim.reporting import render_mapping_report
    from npu_sim.core.errors import NoMappingError

    arch_path = _require_path(args.arch)
    ops_path = _require_path(args.ops)
    try:
        arch = elaborate(str(arch_path))
        ops = load_ops(str(ops_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2
    except (ValueError, FileNotFoundError) as exc:
        sys.stderr.write(f"ops load error: {exc}\n")
        return 2

    try:
        plan = estimate_plan(ops, arch, strict=not args.non_strict)
    except NoMappingError as exc:
        sys.stderr.write(f"mapping error: {exc}\n")
        return 1

    md = render_mapping_report(plan, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0 if not plan.unmapped else 1


def _cmd_reconcile(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import (
        elaborate,
        reconcile,
        reconcile_per_op,
        sink_op_arrivals,
    )
    from npu_sim.evaluation.runner import run_simulation
    from npu_sim.evaluation.trace_ops import load_ops
    from npu_sim.reporting import render_reconcile_report

    arch_path = _require_path(args.arch)
    ops_path = _require_path(args.ops)
    try:
        arch = elaborate(str(arch_path))
        ops = load_ops(str(ops_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2
    except (ValueError, FileNotFoundError) as exc:
        sys.stderr.write(f"ops load error: {exc}\n")
        return 2

    main_clock = arch.clocks[next(iter(arch.clocks))]
    result = run_simulation(arch, max_cycles=args.max_cycles)
    chain = reconcile(
        ops, arch,
        measured_drain_ps=result.drain_time_ps,
        clock_period_ps=main_clock.period_ps,
        strict=False,
    )

    # Per-op needs a sink Consumer exposing received_tokens; auto-detect or use --sink.
    per_op = None
    sink_id = args.sink or _autodetect_sink(arch)
    if sink_id is not None:
        try:
            arrivals = sink_op_arrivals(arch, sink_id)
            per_op = reconcile_per_op(
                ops, arch, arrivals, main_clock.period_ps, strict=False
            )
        except (ValueError, KeyError):
            per_op = None

    md = render_reconcile_report(chain, per_op, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0


def _autodetect_sink(arch) -> Optional[str]:
    """Find a module that exposes received_tokens (a Consumer)."""
    for mid, m in arch.modules.items():
        if hasattr(m, "received_tokens"):
            return mid
    return None


# ============================================================
# Argparse wiring
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m npu_sim",
        description="NPU simulation platform CLI.",
    )
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_list = subparsers.add_parser(
        "list-modules",
        help="List registered IModule and INumericalModel types.",
    )
    p_list.set_defaults(handler=_cmd_list_modules)

    p_sim = subparsers.add_parser(
        "simulate",
        help="Elaborate + run a single architecture DSL file.",
    )
    p_sim.add_argument("dsl", help="Path to the architecture YAML.")
    p_sim.add_argument(
        "--max-cycles",
        type=int,
        default=10_000,
        help="Scheduler step cap (default: 10000).",
    )
    p_sim.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_sim.set_defaults(handler=_cmd_simulate)

    p_cmp = subparsers.add_parser(
        "compare",
        help="Run baseline + variant DSLs and emit a comparison report.",
    )
    p_cmp.add_argument("baseline", help="Path to the baseline architecture YAML.")
    p_cmp.add_argument("variant", help="Path to the variant architecture YAML.")
    p_cmp.add_argument(
        "--max-cycles",
        type=int,
        default=10_000,
        help="Scheduler step cap for each run (default: 10000).",
    )
    p_cmp.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_cmp.set_defaults(handler=_cmd_compare)

    p_trc = subparsers.add_parser(
        "trace",
        help="Render an ASCII cycle-by-cycle waveform of an architecture.",
    )
    p_trc.add_argument("dsl", help="Path to the architecture YAML.")
    p_trc.add_argument(
        "--max-cycles",
        type=int,
        default=500,
        help="Scheduler step cap (default: 500).",
    )
    p_trc.add_argument(
        "--show-cycles",
        type=int,
        default=200,
        help="How many cycles to render in the waveform (default: 200).",
    )
    p_trc.add_argument(
        "--no-condense",
        action="store_true",
        help="Disable condensation of all-idle cycle ranges.",
    )
    p_trc.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_trc.set_defaults(handler=_cmd_trace)

    p_est = subparsers.add_parser(
        "estimate",
        help="Map an operator trace onto an architecture (SPEC-006 static estimate).",
    )
    p_est.add_argument("arch", help="Path to the architecture YAML.")
    p_est.add_argument(
        "ops",
        help="Path to an ops YAML (top-level `ops:` list, or a fixture with a "
        "TraceProducer whose config.ops is reused).",
    )
    p_est.add_argument(
        "--non-strict",
        action="store_true",
        help="Skip unmappable ops instead of erroring.",
    )
    p_est.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_est.set_defaults(handler=_cmd_estimate)

    p_rec = subparsers.add_parser(
        "reconcile",
        help="Join Mapper static estimate against simulated measured drain "
        "(SPEC-006 §8 estimate-vs-measured reconciliation).",
    )
    p_rec.add_argument("arch", help="Path to the architecture YAML.")
    p_rec.add_argument(
        "ops",
        help="Path to an ops YAML (top-level `ops:` list, or a fixture with a "
        "TraceProducer whose config.ops is reused).",
    )
    p_rec.add_argument(
        "--sink",
        default=None,
        help="Sink module_id whose received_tokens carry op_index arrivals "
        "(for the per-op table). Auto-detected if omitted.",
    )
    p_rec.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for the measured run (default: 100000).",
    )
    p_rec.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_rec.set_defaults(handler=_cmd_reconcile)

    return parser


def main(argv: Optional[Sequence[str]] = None, out: Optional[TextIO] = None) -> int:
    """Programmatic entry point. Returns the exit code instead of calling sys.exit.

    `argv` defaults to sys.argv[1:] when None; `out` defaults to sys.stdout.
    Useful for in-process testing.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    out_stream = out if out is not None else sys.stdout
    return args.handler(args, out_stream)


# ============================================================
# Helpers
# ============================================================


def _require_path(value: str) -> Path:
    path = Path(value)
    if not path.exists():
        sys.stderr.write(f"file not found: {path}\n")
        sys.exit(2)
    return path


def _write_output(text: str, out_path: Optional[str], default: TextIO) -> None:
    if out_path:
        Path(out_path).write_text(text + "\n", encoding="utf-8")
    else:
        default.write(text)
        if not text.endswith("\n"):
            default.write("\n")


if __name__ == "__main__":  # pragma: no cover - exercised via `python -m npu_sim`
    sys.exit(main())
