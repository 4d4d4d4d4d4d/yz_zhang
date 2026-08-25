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
    snapshot <arch>             Capture whole-chip state (modules + FIFOs +
                                clock) at a cycle — the QEMU §3.2 savevm data
                                view; restore = deterministic replay.
    snapshot-diff <a> <b>       Diff two architectures' whole-chip state at
                                the same cycle (where inside the chip an A/B
                                pair diverges).
    fidelity <arch>             Report % of chip area on physically-grounded
                                models vs [calibration knob] placeholders.
    energy <arch> <ops>         Total workload energy (dynamic + static) +
                                a PPA one-liner (area / energy / latency).
    bottleneck <arch>           Measure the pipeline throughput bottleneck —
                                the slowest stage on the datapath, with a
                                pipeline-model drain reconciled to measured.
    sweep <base> <m.key> <vals> Sweep one module config knob over values and
                                report the PPA response + bottleneck shift
                                (design-space exploration).
    optimize <base> --knob ...  Greedily widen the bottleneck stage across
                                config knobs until drain stops improving
                                (automated design search).

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


def _cmd_snapshot(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import elaborate, snapshot_at_cycle
    from npu_sim.reporting import render_state_snapshot

    arch_path = _require_path(args.arch)
    try:
        arch = elaborate(str(arch_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    snap = snapshot_at_cycle(arch, at_cycle=args.at_cycle, max_cycles=args.max_cycles)
    md = render_state_snapshot(snap, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0


def _coerce_value(raw: str) -> object:
    """Coerce a CLI sweep value string to int, then float, else keep as str."""
    for caster in (int, float):
        try:
            return caster(raw)
        except ValueError:
            continue
    return raw


def _cmd_optimize(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import optimize_bottleneck
    from npu_sim.reporting import render_optimize_report

    _require_path(args.base)
    knobs: dict[str, list] = {}
    for spec in args.knob or []:
        if "=" not in spec or "." not in spec.split("=", 1)[0]:
            sys.stderr.write(
                f"bad --knob {spec!r}; expected '<module>.<key>=v1,v2,...'\n"
            )
            return 3
        path, vals = spec.split("=", 1)
        values = [_coerce_value(v.strip()) for v in vals.split(",") if v.strip()]
        if len(values) < 2:
            sys.stderr.write(f"--knob {path} needs at least two values\n")
            return 3
        knobs[path.strip()] = values
    if not knobs:
        sys.stderr.write("at least one --knob is required\n")
        return 3

    try:
        report = optimize_bottleneck(
            args.base, knobs, max_cycles=args.max_cycles, max_rounds=args.max_rounds
        )
    except NpuSimError as exc:
        sys.stderr.write(f"optimize error: {exc}\n")
        return 2

    md = render_optimize_report(report)
    _write_output(md, args.out, out)
    return 0


def _cmd_sweep(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import sweep_config
    from npu_sim.reporting import render_sweep_report

    _require_path(args.base)
    if "." not in args.param:
        sys.stderr.write("param must be '<module_id>.<config_key>'\n")
        return 3
    module_id, config_key = args.param.split(".", 1)
    values = [_coerce_value(v.strip()) for v in args.values.split(",") if v.strip()]
    if not values:
        sys.stderr.write("no sweep values given\n")
        return 3

    try:
        report = sweep_config(
            args.base, module_id, config_key, values, max_cycles=args.max_cycles
        )
    except NpuSimError as exc:
        sys.stderr.write(f"sweep error: {exc}\n")
        return 2

    md = render_sweep_report(report)
    _write_output(md, args.out, out)
    return 0


def _cmd_bottleneck(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import analyze_pipeline_bottleneck, elaborate
    from npu_sim.reporting import render_pipeline_bottleneck

    arch_path = _require_path(args.arch)
    try:
        arch = elaborate(str(arch_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    report = analyze_pipeline_bottleneck(arch, max_cycles=args.max_cycles)
    md = render_pipeline_bottleneck(report, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0


def _cmd_energy(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import analyze_energy, elaborate
    from npu_sim.evaluation.trace_ops import load_ops
    from npu_sim.reporting import render_energy_report

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

    report = analyze_energy(ops, arch, max_cycles=args.max_cycles)
    md = render_energy_report(report, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0


def _cmd_fidelity(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import chip_fidelity, elaborate
    from npu_sim.reporting import render_fidelity_report

    arch_path = _require_path(args.arch)
    try:
        arch = elaborate(str(arch_path))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    report = chip_fidelity(arch)
    md = render_fidelity_report(report, arch_name=arch.name)
    _write_output(md, args.out, out)
    return 0


def _cmd_snapshot_diff(args: argparse.Namespace, out: TextIO) -> int:
    from npu_sim.evaluation import diff_snapshots, elaborate, snapshot_at_cycle
    from npu_sim.reporting import render_snapshot_diff

    arch_a = _require_path(args.arch_a)
    arch_b = _require_path(args.arch_b)
    try:
        a = elaborate(str(arch_a))
        b = elaborate(str(arch_b))
    except NpuSimError as exc:
        sys.stderr.write(f"elaboration error: {exc}\n")
        return 2

    snap_a = snapshot_at_cycle(a, at_cycle=args.at_cycle, max_cycles=args.max_cycles)
    snap_b = snapshot_at_cycle(b, at_cycle=args.at_cycle, max_cycles=args.max_cycles)
    diff = diff_snapshots(snap_a, snap_b)
    md = render_snapshot_diff(diff)
    _write_output(md, args.out, out)
    return 0 if diff.identical else 1


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

    p_snap = subparsers.add_parser(
        "snapshot",
        help="Capture whole-chip state at a cycle (QEMU §3.2 savevm data view; "
        "restore = deterministic replay).",
    )
    p_snap.add_argument("arch", help="Path to the architecture YAML.")
    p_snap.add_argument(
        "--at-cycle",
        type=int,
        default=0,
        help="0-based cycle index to capture state at (default: 0). If the "
        "sim drains earlier, the final stable state is captured.",
    )
    p_snap.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for the replay (default: 100000).",
    )
    p_snap.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_snap.set_defaults(handler=_cmd_snapshot)

    p_sdiff = subparsers.add_parser(
        "snapshot-diff",
        help="Diff two architectures' whole-chip state at the same cycle "
        "(where inside the chip an A/B pair diverges).",
    )
    p_sdiff.add_argument("arch_a", help="Path to architecture A YAML.")
    p_sdiff.add_argument("arch_b", help="Path to architecture B YAML.")
    p_sdiff.add_argument(
        "--at-cycle",
        type=int,
        default=0,
        help="0-based cycle index to capture both states at (default: 0).",
    )
    p_sdiff.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for each replay (default: 100000).",
    )
    p_sdiff.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_sdiff.set_defaults(handler=_cmd_snapshot_diff)

    p_bn = subparsers.add_parser(
        "bottleneck",
        help="Measure the pipeline throughput bottleneck — the slowest stage "
        "on the datapath (SPEC-006 §8 throughput attribution).",
    )
    p_bn.add_argument("arch", help="Path to the architecture YAML.")
    p_bn.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for the measured run (default: 100000).",
    )
    p_bn.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_bn.set_defaults(handler=_cmd_bottleneck)

    p_fid = subparsers.add_parser(
        "fidelity",
        help="Report how much of a chip's area is on physically-grounded "
        "models vs [calibration knob] placeholders (SPEC-013).",
    )
    p_fid.add_argument("arch", help="Path to the architecture YAML.")
    p_fid.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_fid.set_defaults(handler=_cmd_fidelity)

    p_en = subparsers.add_parser(
        "energy",
        help="Total workload energy = dynamic (per-op, Horowitz) + static "
        "(power × runtime), with a PPA one-liner (SPEC-013).",
    )
    p_en.add_argument("arch", help="Path to the architecture YAML.")
    p_en.add_argument(
        "ops",
        help="Path to an ops YAML (top-level `ops:` list, or a fixture with a "
        "TraceProducer whose config.ops is reused).",
    )
    p_en.add_argument(
        "--max-cycles", type=int, default=100_000,
        help="Scheduler step cap for the measured run (default: 100000).",
    )
    p_en.add_argument(
        "--out", default=None, help="Optional output file; defaults to stdout.",
    )
    p_en.set_defaults(handler=_cmd_energy)

    p_sw = subparsers.add_parser(
        "sweep",
        help="Sweep one module config knob over values and report the PPA "
        "response + bottleneck shift (design-space exploration).",
    )
    p_sw.add_argument("base", help="Path to the base architecture YAML.")
    p_sw.add_argument(
        "param",
        help="Knob to sweep, as '<module_id>.<config_key>' (e.g. avp.vector_width).",
    )
    p_sw.add_argument(
        "values",
        help="Comma-separated values to try (e.g. '16,32,64').",
    )
    p_sw.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for each run (default: 100000).",
    )
    p_sw.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_sw.set_defaults(handler=_cmd_sweep)

    p_opt = subparsers.add_parser(
        "optimize",
        help="Greedily widen the bottleneck stage across config knobs until "
        "drain stops improving (automated design search).",
    )
    p_opt.add_argument("base", help="Path to the base architecture YAML.")
    p_opt.add_argument(
        "--knob",
        action="append",
        metavar="MODULE.KEY=v1,v2,...",
        help="A knob to search: module config field + ascending candidate "
        "values (cheap→wide). Repeatable. E.g. --knob avp.vector_width=16,32,64.",
    )
    p_opt.add_argument(
        "--max-rounds",
        type=int,
        default=20,
        help="Cap on greedy search rounds (default: 20).",
    )
    p_opt.add_argument(
        "--max-cycles",
        type=int,
        default=100_000,
        help="Scheduler step cap for each run (default: 100000).",
    )
    p_opt.add_argument(
        "--out",
        default=None,
        help="Optional output file; defaults to stdout.",
    )
    p_opt.set_defaults(handler=_cmd_optimize)

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
