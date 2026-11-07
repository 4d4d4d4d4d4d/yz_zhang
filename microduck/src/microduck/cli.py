"""``microduck`` command line entry point."""

from __future__ import annotations

import argparse
import sys


def _cmd_spec(argv: list[str]) -> None:
    from .model import spec
    print(spec.describe())


def _cmd_build_model(argv: list[str]) -> None:
    from .model.builder import write_all
    for path in write_all():
        print(path)


def _cmd_walk(argv: list[str]) -> None:
    """Run the scripted gait -- no trained policy needed."""
    import numpy as np
    from .model import spec
    from .sim.env import EnvConfig, MicroduckEnv
    from .sim.gait import ScriptedGait
    from .sim.randomization import RandomizationConfig

    p = argparse.ArgumentParser(prog="microduck walk")
    p.add_argument("--vx", type=float, default=0.15, help="forward speed command, m/s")
    p.add_argument("--wz", type=float, default=0.0, help="turn rate command, rad/s")
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--randomize", action="store_true",
                   help="draw a random robot instead of the nominal one")
    args = p.parse_args(argv)

    cfg = EnvConfig(episode_length=args.seconds + 1,
                    randomization=RandomizationConfig(enabled=args.randomize))
    env = MicroduckEnv(cfg, seed=0)
    env.reset(seed=0)
    if not args.randomize:
        env.data.qpos[3:7] = (1.0, 0.0, 0.0, 0.0)
        env.data.qvel[:] = 0.0
    gait = ScriptedGait(cfg.gait)
    default = np.array(spec.default_pose())
    command = (args.vx, 0.0, args.wz)
    start = env.data.qpos[:3].copy()

    steps = int(args.seconds / env.dt)
    for step in range(steps):
        env.command[:] = command
        targets = np.array(gait.step(command, env.dt))
        _obs, _r, terminated, _trunc, _info = env.step((targets - default) / cfg.action_scale)
        if terminated:
            print(f"fell after {step * env.dt:.2f}s")
            break
    else:
        delta = env.data.qpos[:3] - start
        print(f"walked {args.seconds:.1f}s, displacement "
              f"({delta[0]:+.3f}, {delta[1]:+.3f}) m, mean speed "
              f"{delta[0] / args.seconds:+.3f} m/s, height {env.data.qpos[2]:.3f} m")


def _cmd_train(argv: list[str]) -> None:
    from .rl.train import main
    main(argv)


def _cmd_evaluate(argv: list[str]) -> None:
    from .rl.evaluate import main
    main(argv)


def _cmd_export(argv: list[str]) -> None:
    from .rl.export_onnx import main
    main(argv)


def _cmd_bench(argv: list[str]) -> None:
    from .rl.bench import main
    main(argv)


COMMANDS = {
    "spec": (_cmd_spec, "print the robot specification"),
    "build-model": (_cmd_build_model, "regenerate the MJCF from spec.py"),
    "walk": (_cmd_walk, "run the scripted gait baseline"),
    "train": (_cmd_train, "train a policy with PPO"),
    "evaluate": (_cmd_evaluate, "evaluate a checkpoint"),
    "export": (_cmd_export, "export a checkpoint to ONNX"),
    "bench": (_cmd_bench, "measure simulation throughput on this machine"),
}


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        width = max(len(name) for name in COMMANDS)
        print("usage: microduck <command> [options]\n\ncommands:")
        for name, (_fn, help_text) in COMMANDS.items():
            print(f"  {name:<{width}}  {help_text}")
        print("\nRun `microduck <command> --help` for a command's options.")
        return
    command = argv[0]
    if command not in COMMANDS:
        print(f"unknown command {command!r}; run `microduck --help`", file=sys.stderr)
        raise SystemExit(2)
    COMMANDS[command][0](argv[1:])


if __name__ == "__main__":
    main()
