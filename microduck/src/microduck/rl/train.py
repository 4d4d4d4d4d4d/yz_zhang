"""Distributed training entry point.

Launch on one 4-GPU box with::

    torchrun --standalone --nproc_per_node=4 -m microduck.rl.train \\
        --config configs/fetch_v100x4.json

or run it directly with no launcher for a single-process debug run.  Every rank
owns its own pool of environment worker processes and its own copy of the
policy; gradients are averaged by DDP, and the curriculum and the KL early-stop
are decided collectively so the ranks cannot diverge.

Read ``docs/training.md`` before changing ``num_envs``: on this model the
throughput ceiling is CPU physics, not the GPUs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path

import numpy as np
import torch
import torch.distributed as dist
from torch import nn

from ..sim.env import EnvConfig, MicroduckEnv
from ..sim.fetch_env import FetchConfig, MicroduckFetchEnv
from .networks import ActorCritic, load_transferred_weights
from .ppo import PPO, PPOConfig, RolloutBuffer
from .vec_env import SubprocVecEnv, SyncVecEnv

TASKS = {"walk": (MicroduckEnv, EnvConfig), "fetch": (MicroduckFetchEnv, FetchConfig)}


@dataclass
class CurriculumConfig:
    """Ramp the task difficulty with measured competence, not with step count.

    The ball starts close and straight ahead; the spawn range and bearing open
    up only once the policy is actually succeeding.  Tying this to success rate
    rather than to a step schedule is what keeps a slow run from being fed a
    difficulty it cannot do anything with.
    """

    enabled: bool = True
    start_difficulty: float = 0.25
    #: Raise difficulty when the success rate clears this, lower it below.
    promote_above: float = 0.55
    demote_below: float = 0.15
    step: float = 0.05
    #: Updates to wait between adjustments, so the statistic has settled.
    patience: int = 10


@dataclass
class TrainConfig:
    task: str = "fetch"
    total_steps: int = 200_000_000          # environment steps, summed over ranks
    seed: int = 1
    ppo: PPOConfig = field(default_factory=PPOConfig)
    curriculum: CurriculumConfig = field(default_factory=CurriculumConfig)

    output_dir: str = "runs/fetch"
    save_interval: int = 50                 # updates
    log_interval: int = 1
    #: Keep this many rolling checkpoints besides ``best`` and ``latest``.
    keep_checkpoints: int = 5

    #: Warm-start from a checkpoint.  A walking checkpoint transfers into the
    #: fetch task exactly; see networks.load_transferred_weights.
    init_from: str = ""
    resume: str = ""

    use_subprocess_envs: bool = True
    #: Worker processes per rank.  0 means auto: the rank's fair share of the
    #: machine's cores, capped at num_envs.  Environments beyond the worker
    #: count are packed into the existing workers, which is faster than giving
    #: each one a process -- one pipe round trip per worker per step instead of
    #: one per environment.  Measure with `microduck bench` on the real box.
    num_workers: int = 0
    #: Threads per rank for MuJoCo/BLAS.  Left at 1 deliberately: the
    #: parallelism that pays here is one process per environment, and letting
    #: each of them spawn its own thread pool oversubscribes the box badly.
    torch_threads: int = 1

    actor_hidden: tuple[int, ...] = (512, 256, 128)
    critic_hidden: tuple[int, ...] = (512, 256, 128)
    init_log_std: float = -1.6

    #: Overrides applied to the environment config, e.g. {"grasp_mode": "contact"}.
    env_overrides: dict = field(default_factory=dict)


def _from_dict(cls, data: dict):
    """Build a (possibly nested) dataclass from plain JSON."""
    kwargs = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        if is_dataclass(f.type) and isinstance(value, dict):
            kwargs[f.name] = _from_dict(f.type, value)
        elif isinstance(value, list) and f.name.endswith("hidden"):
            kwargs[f.name] = tuple(value)
        else:
            kwargs[f.name] = value
    return cls(**kwargs)


def load_config(path: str | None, overrides: dict | None = None) -> TrainConfig:
    data: dict = {}
    if path:
        data = json.loads(Path(path).read_text())
    cfg = TrainConfig(
        ppo=_from_dict(PPOConfig, data.get("ppo", {})),
        curriculum=_from_dict(CurriculumConfig, data.get("curriculum", {})),
        **{k: v for k, v in data.items() if k not in ("ppo", "curriculum")})
    for key, value in (overrides or {}).items():
        if value is not None:
            setattr(cfg, key, value)
    return cfg


# ----------------------------------------------------------------------
# Distributed plumbing
# ----------------------------------------------------------------------
@dataclass
class DistInfo:
    rank: int = 0
    local_rank: int = 0
    world_size: int = 1
    distributed: bool = False

    @property
    def is_main(self) -> bool:
        return self.rank == 0


def setup_distributed() -> DistInfo:
    """Join the process group when launched under torchrun; otherwise no-op."""
    if "RANK" not in os.environ or "WORLD_SIZE" not in os.environ:
        return DistInfo()
    rank = int(os.environ["RANK"])
    world_size = int(os.environ["WORLD_SIZE"])
    local_rank = int(os.environ.get("LOCAL_RANK", rank))
    backend = "nccl" if torch.cuda.is_available() else "gloo"
    dist.init_process_group(backend=backend, rank=rank, world_size=world_size)
    if torch.cuda.is_available():
        torch.cuda.set_device(local_rank)
    return DistInfo(rank, local_rank, world_size, True)


def cleanup_distributed(info: DistInfo) -> None:
    if info.distributed and dist.is_initialized():
        dist.barrier()
        dist.destroy_process_group()


def broadcast_float(value: float, device: torch.device, info: DistInfo) -> float:
    """Agree on one value across ranks, so the curriculum stays in lockstep."""
    if not info.distributed:
        return value
    tensor = torch.tensor([value], device=device)
    dist.broadcast(tensor, src=0)
    return float(tensor.item())


# ----------------------------------------------------------------------
# Environment construction
# ----------------------------------------------------------------------
def make_env_config(cfg: TrainConfig) -> EnvConfig:
    _env_cls, config_cls = TASKS[cfg.task]
    env_cfg = config_cls()
    for key, value in cfg.env_overrides.items():
        if not hasattr(env_cfg, key):
            raise ValueError(f"unknown env override {key!r} for task {cfg.task!r}")
        setattr(env_cfg, key, value)
    if cfg.task == "fetch" and cfg.curriculum.enabled:
        env_cfg.difficulty = cfg.curriculum.start_difficulty
    return env_cfg


class EnvFactory:
    """Picklable env factory -- subprocess workers need to reconstruct it."""

    def __init__(self, task: str, env_cfg: EnvConfig, seed: int) -> None:
        self.task = task
        self.env_cfg = env_cfg
        self.seed = seed

    def __call__(self):
        env_cls, _ = TASKS[self.task]
        return env_cls(self.env_cfg, seed=self.seed)


def default_num_workers(num_envs: int, world_size: int) -> int:
    """This rank's fair share of the machine's cores."""
    cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (
        os.cpu_count() or 1)
    return max(1, min(num_envs, cores // max(1, world_size)))


def build_vec_env(cfg: TrainConfig, info: DistInfo):
    env_cfg = make_env_config(cfg)
    # Every rank gets a disjoint seed block, so 4 ranks explore 4 different
    # slices of the task distribution rather than the same one four times.
    base = cfg.seed + info.rank * 10_000
    factories = [EnvFactory(cfg.task, env_cfg, base + i) for i in range(cfg.ppo.num_envs)]
    if not cfg.use_subprocess_envs:
        return SyncVecEnv(factories)
    workers = cfg.num_workers or default_num_workers(cfg.ppo.num_envs, info.world_size)
    return SubprocVecEnv(factories, start_seed=base, num_workers=workers)


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------
class RunLogger:
    """CSV plus a console line.  No tensorboard dependency, nothing to install."""

    def __init__(self, output_dir: Path, enabled: bool) -> None:
        self.enabled = enabled
        self.path = output_dir / "progress.csv"
        self._writer = None
        self._file = None
        if enabled:
            output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, row: dict[str, float]) -> None:
        if not self.enabled:
            return
        if self._writer is None:
            self._file = self.path.open("a", newline="")
            self._writer = csv.DictWriter(self._file, fieldnames=list(row))
            if self.path.stat().st_size == 0:
                self._writer.writeheader()
        self._writer.writerow({k: row.get(k, "") for k in self._writer.fieldnames})
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()


#: The episode statistics reduced across ranks, in a fixed order.
#: Fixed, because the number of collectives a rank issues per update must not
#: depend on its own data: a rank that happened to finish no episodes this
#: update would then issue fewer all-reduces than its peers and deadlock the
#: whole job.  So every rank always reduces the same tensor, carrying a count
#: of zero where it has nothing to contribute.
SHARED_STAT_KEYS: tuple[str, ...] = ("ep_return", "ep_length", "success_rate", "reached_phase")


def reduce_episode_stats(stats: "EpisodeStats", device: torch.device,
                         info: DistInfo) -> dict[str, float]:
    """Pool the rolling episode statistics over all ranks in one collective.

    Each key is reduced as a (sum, count) pair, so the result is the mean over
    every episode the job finished, not the mean of per-rank means -- which
    would weight a rank that finished two episodes the same as one that
    finished fifty.
    """
    sums, counts = [], []
    for key in SHARED_STAT_KEYS:
        values = stats.values_for(key)
        sums.append(float(np.sum(values)) if values else 0.0)
        counts.append(float(len(values)))
    packed = torch.tensor(sums + counts, dtype=torch.float64, device=device)
    if info.distributed:
        dist.all_reduce(packed, op=dist.ReduceOp.SUM)
    n = len(SHARED_STAT_KEYS)
    totals, totals_count = packed[:n], packed[n:]
    return {key: float(totals[i] / totals_count[i])
            for i, key in enumerate(SHARED_STAT_KEYS) if totals_count[i] > 0}


class EpisodeStats:
    """Rolling window of finished-episode statistics."""

    def __init__(self, window: int = 200) -> None:
        self.window = window
        self.returns: list[float] = []
        self.lengths: list[int] = []
        self.successes: list[float] = []
        self.reached: list[float] = []
        self._running = None

    def start(self, num_envs: int) -> None:
        self._running = np.zeros(num_envs)
        self._steps = np.zeros(num_envs, dtype=int)

    def update(self, rewards: np.ndarray, dones: np.ndarray, infos: list[dict]) -> None:
        self._running += rewards
        self._steps += 1
        for i, done in enumerate(dones):
            if not done:
                continue
            self._append(self.returns, float(self._running[i]))
            self._append(self.lengths, int(self._steps[i]))
            info = infos[i]
            if "success" in info:
                self._append(self.successes, float(bool(info["success"])))
                self._append(self.reached, float(info.get("reached_phase", 0)))
            self._running[i] = 0.0
            self._steps[i] = 0

    def values_for(self, key: str) -> list:
        return {"ep_return": self.returns, "ep_length": self.lengths,
                "success_rate": self.successes, "reached_phase": self.reached}[key]

    def _append(self, store: list, value) -> None:
        store.append(value)
        if len(store) > self.window:
            del store[0]

    def summary(self) -> dict[str, float]:
        out = {
            "ep_return": float(np.mean(self.returns)) if self.returns else float("nan"),
            "ep_length": float(np.mean(self.lengths)) if self.lengths else float("nan"),
        }
        if self.successes:
            out["success_rate"] = float(np.mean(self.successes))
            out["reached_phase"] = float(np.mean(self.reached))
        return out


# ----------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------
def train(cfg: TrainConfig) -> Path:
    info = setup_distributed()
    torch.manual_seed(cfg.seed + info.rank)
    np.random.seed(cfg.seed + info.rank)
    torch.set_num_threads(max(1, cfg.torch_threads))

    device = torch.device(f"cuda:{info.local_rank}" if torch.cuda.is_available() else "cpu")
    output_dir = Path(cfg.output_dir)
    logger = RunLogger(output_dir, info.is_main)
    if info.is_main:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "config.json").write_text(json.dumps(asdict(cfg), indent=2, default=list))

    vec = build_vec_env(cfg, info)
    policy = ActorCritic(vec.observation_dim, vec.action_dim,
                         actor_hidden=tuple(cfg.actor_hidden),
                         critic_hidden=tuple(cfg.critic_hidden),
                         init_log_std=cfg.init_log_std).to(device)

    if cfg.init_from:
        state = torch.load(cfg.init_from, map_location=device, weights_only=True)
        report = load_transferred_weights(policy, state.get("policy", state))
        if info.is_main:
            padded = {k: v for k, v in report.items() if v != "copied"}
            print(f"[init] warm-started from {cfg.init_from}; "
                  f"{len(report) - len(padded)} tensors copied verbatim")
            for key, note in padded.items():
                print(f"[init]   {key}: {note}")

    wrapped: nn.Module = policy
    if info.distributed:
        wrapped = nn.parallel.DistributedDataParallel(
            policy, device_ids=[info.local_rank] if device.type == "cuda" else None)

    steps_per_update = cfg.ppo.batch_size(info.world_size)
    total_updates = max(1, cfg.total_steps // steps_per_update)
    algo = PPO(wrapped, cfg.ppo, device, total_updates=total_updates,
               world_size=info.world_size)

    start_update = 0
    best_metric = -float("inf")
    if cfg.resume:
        state = torch.load(cfg.resume, map_location=device, weights_only=False)
        algo.load_state_dict(state)
        start_update = int(state.get("update", 0))
        best_metric = float(state.get("best_metric", -float("inf")))
        if info.is_main:
            print(f"[resume] {cfg.resume} at update {start_update}")

    buffer = RolloutBuffer(cfg.ppo.rollout_steps, cfg.ppo.num_envs,
                           vec.observation_dim, vec.action_dim, device)
    stats = EpisodeStats()
    stats.start(cfg.ppo.num_envs)

    obs = torch.as_tensor(vec.reset(seed=cfg.seed + info.rank * 10_000),
                          dtype=torch.float32, device=device)
    difficulty = cfg.curriculum.start_difficulty if cfg.curriculum.enabled else 1.0
    last_adjust = start_update
    start_time = time.time()

    if info.is_main:
        workers = getattr(vec, "num_workers", 1)
        print(f"[setup] task={cfg.task} obs={vec.observation_dim} act={vec.action_dim}\n"
              f"[setup] ranks={info.world_size} envs/rank={cfg.ppo.num_envs} "
              f"workers/rank={workers} batch={steps_per_update} "
              f"updates={total_updates} device={device}")

    for update in range(start_update, total_updates):
        buffer.reset()
        for _ in range(cfg.ppo.rollout_steps):
            with torch.no_grad():
                action, log_prob, value = policy.act(obs)
            next_obs, rewards, dones, infos = vec.step(action.cpu().numpy())
            stats.update(rewards, dones, infos)
            buffer.add(obs, action, log_prob,
                       torch.as_tensor(rewards, dtype=torch.float32, device=device),
                       torch.as_tensor(dones, dtype=torch.float32, device=device), value)
            obs = torch.as_tensor(next_obs, dtype=torch.float32, device=device)

        with torch.no_grad():
            last_value = policy.value(obs)
        buffer.compute_returns(last_value, cfg.ppo.gamma, cfg.ppo.gae_lambda)
        metrics = algo.update(buffer, update)

        # Pool episode statistics over ranks, so the logged numbers describe
        # the whole job and the curriculum reacts to the whole job.
        shared = reduce_episode_stats(stats, device, info)

        difficulty, last_adjust = _maybe_adjust_curriculum(
            cfg, vec, info, device, difficulty, last_adjust, update, shared.get("success_rate"))

        env_steps = (update + 1) * steps_per_update
        if info.is_main and update % cfg.log_interval == 0:
            elapsed = time.time() - start_time
            row = {"update": update, "env_steps": env_steps,
                   "steps_per_sec": env_steps / max(elapsed, 1e-6),
                   "difficulty": difficulty, **shared, **metrics}
            logger.write(row)
            fields_str = "  ".join(
                f"{k}={row[k]:.3f}" for k in ("ep_return", "success_rate", "reached_phase")
                if k in row)
            print(f"[{update:>6}] steps={env_steps:>11,} "
                  f"sps={row['steps_per_sec']:>8,.0f}  {fields_str}  "
                  f"kl={metrics['approx_kl']:.4f}  diff={difficulty:.2f}", flush=True)

        if info.is_main:
            metric = shared.get("success_rate", shared.get("ep_return", -float("inf")))
            if metric > best_metric:
                best_metric = metric
                _save(algo, output_dir / "best.pt", update, best_metric, cfg)
            if update % cfg.save_interval == 0 or update == total_updates - 1:
                _save(algo, output_dir / "latest.pt", update, best_metric, cfg)
                _save(algo, output_dir / f"update_{update:07d}.pt", update, best_metric, cfg)
                _prune_checkpoints(output_dir, cfg.keep_checkpoints)

    vec.close()
    logger.close()
    cleanup_distributed(info)
    return output_dir / "best.pt"


def _maybe_adjust_curriculum(cfg, vec, info, device, difficulty, last_adjust,
                             update, success_rate):
    cur = cfg.curriculum
    if not (cur.enabled and cfg.task == "fetch"):
        return difficulty, last_adjust
    if success_rate is None or update - last_adjust < cur.patience:
        return difficulty, last_adjust

    target = difficulty
    if success_rate > cur.promote_above:
        target = min(1.0, difficulty + cur.step)
    elif success_rate < cur.demote_below:
        target = max(0.05, difficulty - cur.step)
    # Rank 0 decides and broadcasts; otherwise rounding differences could leave
    # ranks training on different task distributions.
    target = broadcast_float(target, device, info)
    if abs(target - difficulty) > 1e-9:
        if hasattr(vec, "set_env_attr"):
            vec.set_env_attr("difficulty", target)
        else:
            for env in vec.envs:
                env.cfg.difficulty = target
        return target, update
    return difficulty, last_adjust


def _save(algo: PPO, path: Path, update: int, best_metric: float, cfg: TrainConfig) -> None:
    state = algo.state_dict()
    state.update({"update": update + 1, "best_metric": best_metric,
                  "obs_dim": algo.module.obs_dim, "action_dim": algo.module.action_dim,
                  "task": cfg.task})
    tmp = path.with_suffix(".tmp")
    torch.save(state, tmp)
    tmp.replace(path)   # atomic, so a crash mid-save cannot corrupt a checkpoint


def _prune_checkpoints(output_dir: Path, keep: int) -> None:
    rolling = sorted(output_dir.glob("update_*.pt"))
    for path in rolling[:-keep] if keep > 0 else rolling:
        path.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Train a Microduck policy with PPO.")
    p.add_argument("--config", help="JSON config; CLI flags override it")
    p.add_argument("--task", choices=sorted(TASKS))
    p.add_argument("--total-steps", type=int)
    p.add_argument("--num-envs", type=int, help="environments per rank")
    p.add_argument("--rollout-steps", type=int)
    p.add_argument("--learning-rate", type=float)
    p.add_argument("--seed", type=int)
    p.add_argument("--output-dir")
    p.add_argument("--init-from", help="checkpoint to warm-start from")
    p.add_argument("--resume", help="checkpoint to resume training from")
    p.add_argument("--grasp-mode", choices=("weld", "contact"))
    p.add_argument("--no-heading-command", action="store_true",
                   help="make the policy learn navigation too")
    p.add_argument("--no-curriculum", action="store_true")
    p.add_argument("--amp", action="store_true", help="fp16 autocast (see PPOConfig.amp)")
    p.add_argument("--num-workers", type=int,
                   help="worker processes per rank (0 = auto)")
    p.add_argument("--sync-envs", action="store_true",
                   help="run envs in-process; for debugging only")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config, {
        "task": args.task, "total_steps": args.total_steps, "seed": args.seed,
        "output_dir": args.output_dir, "init_from": args.init_from, "resume": args.resume,
    })
    if args.num_envs:
        cfg.ppo.num_envs = args.num_envs
    if args.rollout_steps:
        cfg.ppo.rollout_steps = args.rollout_steps
    if args.learning_rate:
        cfg.ppo.learning_rate = args.learning_rate
    if args.amp:
        cfg.ppo.amp = True
    if args.num_workers is not None:
        cfg.num_workers = args.num_workers
    if args.sync_envs:
        cfg.use_subprocess_envs = False
    if args.no_curriculum:
        cfg.curriculum.enabled = False
    if args.grasp_mode:
        cfg.env_overrides["grasp_mode"] = args.grasp_mode
    if args.no_heading_command:
        cfg.env_overrides["heading_command"] = False
    path = train(cfg)
    print(f"[done] best checkpoint: {path}")


if __name__ == "__main__":
    main()
