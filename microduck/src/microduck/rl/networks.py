"""Actor-critic network.

A plain MLP, deliberately: the policy has to run at 50 Hz on the robot's
onboard computer, and after ONNX export an MLP of this size costs tens of
microseconds per inference.  Anything recurrent or convolutional would have to
earn its keep against that budget.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn
from torch.distributions import Normal


def mlp(in_dim: int, hidden: tuple[int, ...], out_dim: int,
        activation: type[nn.Module] = nn.ELU) -> nn.Sequential:
    layers: list[nn.Module] = []
    last = in_dim
    for size in hidden:
        layers += [nn.Linear(last, size), activation()]
        last = size
    layers.append(nn.Linear(last, out_dim))
    return nn.Sequential(*layers)


def orthogonal_init(module: nn.Sequential, final_gain: float) -> None:
    """Orthogonal init with a small final layer.

    The small last layer matters more than it looks: it makes the initial
    policy stay near the default pose, so the first rollouts are a duck
    standing still rather than a duck immediately throwing itself at the floor.
    """
    linears = [m for m in module if isinstance(m, nn.Linear)]
    for layer in linears[:-1]:
        nn.init.orthogonal_(layer.weight, gain=np.sqrt(2))
        nn.init.zeros_(layer.bias)
    nn.init.orthogonal_(linears[-1].weight, gain=final_gain)
    nn.init.zeros_(linears[-1].bias)


class ActorCritic(nn.Module):
    """Gaussian policy with a state-independent, learned log-std."""

    def __init__(self, obs_dim: int, action_dim: int,
                 actor_hidden: tuple[int, ...] = (512, 256, 128),
                 critic_hidden: tuple[int, ...] = (512, 256, 128),
                 init_log_std: float = -1.6) -> None:
        super().__init__()
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.actor = mlp(obs_dim, actor_hidden, action_dim)
        self.critic = mlp(obs_dim, critic_hidden, 1)
        orthogonal_init(self.actor, final_gain=0.01)
        orthogonal_init(self.critic, final_gain=1.0)
        self.log_std = nn.Parameter(torch.full((action_dim,), float(init_log_std)))

    def distribution(self, obs: torch.Tensor) -> Normal:
        mean = self.actor(obs)
        # Clamped so a collapsing or exploding std cannot produce NaN actions
        # halfway through a long run.
        return Normal(mean, self.log_std.clamp(-5.0, 1.0).exp().expand_as(mean))

    def value(self, obs: torch.Tensor) -> torch.Tensor:
        return self.critic(obs).squeeze(-1)

    @torch.no_grad()
    def act(self, obs: torch.Tensor, deterministic: bool = False):
        dist = self.distribution(obs)
        action = dist.mean if deterministic else dist.sample()
        return action, dist.log_prob(action).sum(-1), self.value(obs)

    def evaluate(self, obs: torch.Tensor, actions: torch.Tensor):
        dist = self.distribution(obs)
        return (dist.log_prob(actions).sum(-1), dist.entropy().sum(-1), self.value(obs))

    def forward(self, obs: torch.Tensor, actions: torch.Tensor | None = None):
        """Deterministic action, or the PPO evaluation when ``actions`` is given.

        Both paths go through ``forward`` on purpose.  Under
        ``DistributedDataParallel`` only a call to the *wrapper* engages the
        gradient reducer: calling ``module.evaluate()`` directly would run fine
        on one GPU and silently train four independent policies on four, since
        no gradient would ever be all-reduced.  Keeping the training path in
        ``forward`` makes that mistake impossible.

        With ``actions=None`` it returns the deterministic action, which is the
        signature exported to ONNX for the robot.
        """
        if actions is None:
            return self.actor(obs)
        return self.evaluate(obs, actions)


def load_transferred_weights(model: ActorCritic, state_dict: dict,
                             strict_tail: bool = False) -> dict[str, str]:
    """Warm-start from a checkpoint trained on a *prefix* of this observation.

    The fetch observation is the walking observation with task channels
    appended, so a walking policy transfers exactly: every weight is reused and
    the new input columns start at zero, which makes the fetch policy's first
    rollouts identical to the walking policy's behaviour.  Mismatched action
    heads are reported rather than silently dropped.
    """
    report: dict[str, str] = {}
    own = model.state_dict()
    for key, target in own.items():
        if key not in state_dict:
            report[key] = "missing in checkpoint, left at init"
            continue
        source = state_dict[key]
        if source.shape == target.shape:
            target.copy_(source)
            report[key] = "copied"
        elif (source.dim() == target.dim() == 2 and source.shape[0] == target.shape[0]
              and source.shape[1] < target.shape[1]):
            target.zero_()
            target[:, :source.shape[1]].copy_(source)
            report[key] = f"padded {tuple(source.shape)} -> {tuple(target.shape)}"
        else:
            if strict_tail:
                raise ValueError(f"cannot transfer {key}: {tuple(source.shape)} -> "
                                 f"{tuple(target.shape)}")
            report[key] = f"shape mismatch {tuple(source.shape)} vs {tuple(target.shape)}, skipped"
    model.load_state_dict(own)
    return report
