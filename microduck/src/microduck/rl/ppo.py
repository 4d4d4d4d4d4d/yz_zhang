"""PPO, with the pieces a multi-GPU run actually needs.

Written against ``torch.distributed`` directly rather than a framework, because
the interesting parts of a multi-GPU PPO run -- how advantages are normalised
across ranks, when the KL early-stop fires, how the curriculum is kept in sync
-- are exactly the parts frameworks hide, and they are where multi-GPU runs go
subtly wrong.  Single-process runs take the same path with a world size of one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.distributed as dist
from torch import nn

from .networks import ActorCritic


@dataclass
class PPOConfig:
    # Rollout shape.  Batch per update = world_size * num_envs * rollout_steps.
    num_envs: int = 32
    rollout_steps: int = 48
    num_minibatches: int = 4
    update_epochs: int = 5

    # Objective.
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    #: Clipping the value loss as well; helps when a one-time task bonus makes
    #: returns jump by two orders of magnitude between episodes.
    clip_range_value: float = 0.4
    value_coef: float = 0.5
    entropy_coef: float = 0.004
    max_grad_norm: float = 1.0

    # Optimiser.
    learning_rate: float = 3.0e-4
    #: Linear decay to this fraction of the initial rate by the last update.
    final_lr_fraction: float = 0.1
    #: Stop the epoch loop early when the policy has moved this far; the single
    #: most effective guard against a collapse late in a long run.
    target_kl: float = 0.02
    #: Normalise advantages over the whole global batch, not per rank.  With
    #: 4 ranks and a sparse task bonus, per-rank normalisation gives the four
    #: ranks materially different gradients.
    global_advantage_norm: bool = True

    # Precision.  Off by default: the network is ~0.4M parameters, so a
    # V100-class run is bounded by CPU physics, not by matmul throughput, and
    # fp16 buys little while adding a scaler to go wrong.  Turn it on if you
    # scale the network up.
    amp: bool = False

    def batch_size(self, world_size: int) -> int:
        return world_size * self.num_envs * self.rollout_steps

    def minibatch_size(self, world_size: int) -> int:
        per_rank = self.num_envs * self.rollout_steps
        if per_rank % self.num_minibatches:
            raise ValueError(
                f"num_envs * rollout_steps ({per_rank}) must be divisible by "
                f"num_minibatches ({self.num_minibatches})")
        return per_rank // self.num_minibatches


class RolloutBuffer:
    """Fixed-size on-policy storage for one rank's share of a batch."""

    def __init__(self, steps: int, num_envs: int, obs_dim: int, action_dim: int,
                 device: torch.device) -> None:
        shape = (steps, num_envs)
        self.obs = torch.zeros(*shape, obs_dim, device=device)
        self.actions = torch.zeros(*shape, action_dim, device=device)
        self.log_probs = torch.zeros(*shape, device=device)
        self.rewards = torch.zeros(*shape, device=device)
        self.dones = torch.zeros(*shape, device=device)
        self.values = torch.zeros(*shape, device=device)
        self.advantages = torch.zeros(*shape, device=device)
        self.returns = torch.zeros(*shape, device=device)
        self.steps = steps
        self.num_envs = num_envs
        self.ptr = 0

    def add(self, obs, action, log_prob, reward, done, value) -> None:
        i = self.ptr
        self.obs[i] = obs
        self.actions[i] = action
        self.log_probs[i] = log_prob
        self.rewards[i] = reward
        self.dones[i] = done
        self.values[i] = value
        self.ptr += 1

    def reset(self) -> None:
        self.ptr = 0

    def compute_returns(self, last_value: torch.Tensor, gamma: float, lam: float) -> None:
        """Truncated GAE.

        ``dones`` here means "the episode ended on this step", which includes
        time-limit truncation.  Bootstrapping is cut at both, which slightly
        under-values states near the time limit; it is the standard trade and it
        keeps a fall and a timeout from being valued the same.
        """
        advantage = torch.zeros(self.num_envs, device=self.rewards.device)
        for t in reversed(range(self.steps)):
            not_done = 1.0 - self.dones[t]
            next_value = last_value if t == self.steps - 1 else self.values[t + 1]
            delta = self.rewards[t] + gamma * next_value * not_done - self.values[t]
            advantage = delta + gamma * lam * not_done * advantage
            self.advantages[t] = advantage
        self.returns = self.advantages + self.values

    def flat(self) -> dict[str, torch.Tensor]:
        return {
            "obs": self.obs.reshape(-1, self.obs.shape[-1]),
            "actions": self.actions.reshape(-1, self.actions.shape[-1]),
            "log_probs": self.log_probs.reshape(-1),
            "advantages": self.advantages.reshape(-1),
            "returns": self.returns.reshape(-1),
            "values": self.values.reshape(-1),
        }


def all_reduce_mean(value: torch.Tensor) -> torch.Tensor:
    if dist.is_available() and dist.is_initialized():
        dist.all_reduce(value, op=dist.ReduceOp.SUM)
        value /= dist.get_world_size()
    return value


def global_mean_std(tensor: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Mean and std of a tensor across every rank."""
    if not (dist.is_available() and dist.is_initialized()):
        return tensor.mean(), tensor.std()
    count = torch.tensor([tensor.numel()], dtype=torch.float64, device=tensor.device)
    total = tensor.double().sum().reshape(1)
    dist.all_reduce(count, op=dist.ReduceOp.SUM)
    dist.all_reduce(total, op=dist.ReduceOp.SUM)
    mean = total / count
    sq = ((tensor.double() - mean) ** 2).sum().reshape(1)
    dist.all_reduce(sq, op=dist.ReduceOp.SUM)
    return mean.float().squeeze(), (sq / count).sqrt().float().squeeze()


class PPO:
    """The update step.  Rollout collection lives in :mod:`microduck.rl.train`."""

    def __init__(self, policy: ActorCritic, cfg: PPOConfig, device: torch.device,
                 total_updates: int, world_size: int = 1) -> None:
        self.cfg = cfg
        self.device = device
        self.world_size = world_size
        self.total_updates = max(1, total_updates)
        #: ``policy`` may be a DDP wrapper; keep a handle on the real module for
        #: checkpointing and for inference outside the update.
        self.wrapped = policy
        self.module: ActorCritic = policy.module if isinstance(
            policy, nn.parallel.DistributedDataParallel) else policy
        self.optimizer = torch.optim.Adam(self.module.parameters(), lr=cfg.learning_rate,
                                          eps=1e-5)
        self.scaler = torch.amp.GradScaler("cuda", enabled=cfg.amp and device.type == "cuda")

    def learning_rate_at(self, update: int) -> float:
        progress = min(1.0, update / self.total_updates)
        floor = self.cfg.final_lr_fraction
        return self.cfg.learning_rate * (1.0 - (1.0 - floor) * progress)

    def update(self, buffer: RolloutBuffer, update_index: int) -> dict[str, float]:
        cfg = self.cfg
        lr = self.learning_rate_at(update_index)
        for group in self.optimizer.param_groups:
            group["lr"] = lr

        batch = buffer.flat()
        advantages = batch["advantages"]
        if cfg.global_advantage_norm:
            mean, std = global_mean_std(advantages)
        else:
            mean, std = advantages.mean(), advantages.std()
        advantages = (advantages - mean) / (std + 1e-8)

        minibatch_size = cfg.minibatch_size(self.world_size)
        indices = np.arange(batch["obs"].shape[0])
        stats = {k: 0.0 for k in ("policy_loss", "value_loss", "entropy", "approx_kl",
                                  "clip_fraction", "grad_norm")}
        count = 0
        stop = False

        for _epoch in range(cfg.update_epochs):
            np.random.shuffle(indices)
            for start in range(0, len(indices), minibatch_size):
                mb = torch.as_tensor(indices[start:start + minibatch_size],
                                     device=self.device)
                mb_adv = advantages[mb]

                with torch.autocast("cuda", dtype=torch.float16,
                                    enabled=cfg.amp and self.device.type == "cuda"):
                    # Through the wrapper, so DDP all-reduces the gradients.
                    log_probs, entropy, values = self.wrapped(
                        batch["obs"][mb], batch["actions"][mb])

                    ratio = (log_probs - batch["log_probs"][mb]).exp()
                    policy_loss = -torch.min(
                        ratio * mb_adv,
                        ratio.clamp(1 - cfg.clip_range, 1 + cfg.clip_range) * mb_adv).mean()

                    old_values = batch["values"][mb]
                    clipped = old_values + (values - old_values).clamp(
                        -cfg.clip_range_value, cfg.clip_range_value)
                    value_loss = 0.5 * torch.max((values - batch["returns"][mb]) ** 2,
                                                 (clipped - batch["returns"][mb]) ** 2).mean()
                    entropy_loss = entropy.mean()
                    loss = policy_loss + cfg.value_coef * value_loss - cfg.entropy_coef * entropy_loss

                self.optimizer.zero_grad(set_to_none=True)
                self.scaler.scale(loss).backward()
                self.scaler.unscale_(self.optimizer)
                grad_norm = nn.utils.clip_grad_norm_(self.module.parameters(),
                                                     cfg.max_grad_norm)
                self.scaler.step(self.optimizer)
                self.scaler.update()

                with torch.no_grad():
                    approx_kl = ((ratio - 1.0) - (log_probs - batch["log_probs"][mb])).mean()
                    clip_fraction = ((ratio - 1.0).abs() > cfg.clip_range).float().mean()

                stats["policy_loss"] += policy_loss.item()
                stats["value_loss"] += value_loss.item()
                stats["entropy"] += entropy_loss.item()
                stats["approx_kl"] += approx_kl.item()
                stats["clip_fraction"] += clip_fraction.item()
                stats["grad_norm"] += float(grad_norm)
                count += 1

            # Every rank must leave the epoch loop on the same update, or the
            # next all-reduce deadlocks.  So the decision is made collectively.
            kl = torch.tensor([approx_kl.item()], device=self.device)
            all_reduce_mean(kl)
            if cfg.target_kl > 0 and float(kl) > cfg.target_kl:
                stop = True
            if stop:
                break

        out = {k: v / max(count, 1) for k, v in stats.items()}
        out["learning_rate"] = lr
        out["early_stopped"] = float(stop)
        out["log_std"] = self.module.log_std.detach().mean().item()
        return out

    def state_dict(self) -> dict:
        return {
            "policy": self.module.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "scaler": self.scaler.state_dict(),
            "config": asdict(self.cfg),
        }

    def load_state_dict(self, state: dict) -> None:
        self.module.load_state_dict(state["policy"])
        self.optimizer.load_state_dict(state["optimizer"])
        if "scaler" in state:
            self.scaler.load_state_dict(state["scaler"])
