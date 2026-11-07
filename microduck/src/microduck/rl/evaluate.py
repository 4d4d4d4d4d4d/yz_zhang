"""Evaluate a checkpoint, with the task statistics that actually matter.

A mean return tells you almost nothing about a staged task: a policy that walks
beautifully and never closes its beak can out-score one that fetches the ball
slowly.  So this reports how far through the sequence each episode got, and the
delivery rate, which is the number the task is really judged on.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from ..sim.env import EnvConfig, MicroduckEnv
from ..sim.fetch_env import FetchConfig, MicroduckFetchEnv, Phase
from ..sim.randomization import RandomizationConfig
from .export_onnx import load_policy

PHASE_NAMES = {int(p): p.name for p in Phase}


def evaluate(checkpoint: str | Path, episodes: int = 50, task: str = "",
             deterministic: bool = True, randomize: bool = True,
             seed: int = 0, render_path: str | None = None) -> dict:
    policy, state = load_policy(checkpoint)
    task = task or str(state.get("task", "fetch"))

    if task == "fetch":
        cfg = FetchConfig()
        env_cls = MicroduckFetchEnv
    else:
        cfg = EnvConfig()
        env_cls = MicroduckEnv
    if not randomize:
        cfg.randomization = RandomizationConfig(enabled=False)
    env = env_cls(cfg, seed=seed)

    returns, lengths, reached, successes, falls = [], [], [], [], []
    for episode in range(episodes):
        obs, _ = env.reset(seed=seed + episode)
        total = 0.0
        steps = 0
        terminated = False
        while True:
            with torch.no_grad():
                action, _, _ = policy.act(
                    torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0),
                    deterministic=deterministic)
            obs, reward, terminated, truncated, info = env.step(action.squeeze(0).numpy())
            total += reward
            steps += 1
            if terminated or truncated:
                break
        returns.append(total)
        lengths.append(steps * env.dt)
        if task == "fetch":
            successes.append(float(info.get("success", False)))
            reached.append(int(info.get("reached_phase", 0)))
            # A fall is a termination that is not a success.
            falls.append(float(terminated and not info.get("success", False)))

    result = {
        "episodes": episodes,
        "return_mean": float(np.mean(returns)),
        "return_std": float(np.std(returns)),
        "episode_seconds_mean": float(np.mean(lengths)),
    }
    if task == "fetch":
        result["success_rate"] = float(np.mean(successes))
        result["fall_rate"] = float(np.mean(falls))
        counts = Counter(reached)
        result["furthest_phase"] = {
            PHASE_NAMES[phase]: counts.get(phase, 0) / episodes for phase in PHASE_NAMES}
    return result


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Evaluate a Microduck policy.")
    p.add_argument("checkpoint")
    p.add_argument("-n", "--episodes", type=int, default=50)
    p.add_argument("--task", default="", choices=("", "walk", "fetch"))
    p.add_argument("--stochastic", action="store_true",
                   help="sample actions instead of using the policy mean")
    p.add_argument("--no-randomize", action="store_true",
                   help="evaluate on the nominal robot only")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    result = evaluate(args.checkpoint, args.episodes, args.task,
                      deterministic=not args.stochastic,
                      randomize=not args.no_randomize, seed=args.seed)
    width = max(len(k) for k in result)
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for name, share in value.items():
                print(f"  {name:<12} {share:6.1%}")
        elif isinstance(value, float):
            print(f"{key:<{width}}  {value:.4f}")
        else:
            print(f"{key:<{width}}  {value}")


if __name__ == "__main__":
    main()
