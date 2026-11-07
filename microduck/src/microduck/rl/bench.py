"""Measure simulation throughput on the machine you are about to train on.

The numbers in ``docs/training.md`` were measured on a 4-core container.  Run
this on the real box before committing to a configuration: on this model the
training rate is set by CPU physics, not by the GPUs, so ``num_envs`` and
``num_workers`` are the knobs that matter and the right values depend entirely
on how many cores each rank gets.
"""

from __future__ import annotations

import argparse
import os
import time

import numpy as np

from .train import TASKS, EnvFactory, make_env_config, TrainConfig
from .vec_env import SubprocVecEnv


def measure(task: str, num_envs: int, num_workers: int, steps: int,
            warmup: int = 10) -> dict[str, float]:
    cfg = TrainConfig(task=task)
    env_cfg = make_env_config(cfg)
    factories = [EnvFactory(task, env_cfg, 1000 + i) for i in range(num_envs)]
    vec = SubprocVecEnv(factories, start_seed=1000, num_workers=num_workers)
    try:
        vec.reset(seed=0)
        actions = np.zeros((num_envs, vec.action_dim), dtype=np.float32)
        for _ in range(warmup):
            vec.step(actions)
        start = time.perf_counter()
        for _ in range(steps):
            vec.step(actions)
        elapsed = time.perf_counter() - start
    finally:
        vec.close()
    total = steps * num_envs / elapsed
    return {"num_envs": num_envs, "num_workers": vec.num_workers,
            "steps_per_sec": total, "per_env": total / num_envs}


def main(argv: list[str] | None = None) -> None:
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (
        os.cpu_count() or 1)
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--task", default="fetch", choices=sorted(TASKS))
    p.add_argument("--envs", type=int, nargs="+",
                   default=[cores, cores * 2, cores * 4, cores * 8])
    p.add_argument("--workers", type=int, default=0,
                   help="worker processes (0 = one per core available here)")
    p.add_argument("--steps", type=int, default=200)
    p.add_argument("--ranks", type=int, default=1,
                   help="GPUs you will train on; divides the cores per rank")
    args = p.parse_args(argv)

    workers = args.workers or max(1, cores // max(1, args.ranks))
    print(f"cores visible: {cores}   ranks planned: {args.ranks}   "
          f"workers per rank: {workers}")
    print(f"{'envs':>6} {'workers':>8} {'env-steps/s':>13} {'per env':>9}")
    best = None
    for num_envs in args.envs:
        result = measure(args.task, num_envs, min(workers, num_envs), args.steps)
        print(f"{result['num_envs']:>6} {result['num_workers']:>8} "
              f"{result['steps_per_sec']:>13,.0f} {result['per_env']:>9,.0f}")
        if best is None or result["steps_per_sec"] > best["steps_per_sec"]:
            best = result

    assert best is not None
    per_rank = best["steps_per_sec"]
    total = per_rank * args.ranks
    print(f"\nbest here: {best['num_envs']} envs over {best['num_workers']} workers "
          f"= {per_rank:,.0f} env-steps/s per rank")
    print(f"with {args.ranks} rank(s), expect roughly {total:,.0f} env-steps/s "
          f"if the box has {workers * args.ranks} cores to give")
    for budget in (100e6, 300e6):
        hours = budget / max(total, 1.0) / 3600
        print(f"  {budget/1e6:>5.0f}M env steps -> {hours:5.1f} h")
    print("\nNote: run this with --ranks set to your GPU count, on the training "
          "box. Throughput here is capped by CPU physics, not by the GPUs.")


if __name__ == "__main__":
    main()
