"""Rectified flow: the continuous half of Atlas' objective.

Atlas generates images and depth maps by progressively denoising them, and is
trained as a rectified-flow model.  Rectified flow defines the straight-line
interpolant between noise and data

    x_t = (1 - t) * eps + t * x_1,        eps ~ N(0, I),  t in [0, 1]

whose exact velocity is the constant ``dx_t/dt = x_1 - eps``.  The network
regresses that velocity; sampling integrates it from ``t = 0`` to ``t = 1``.
Because the path is straight, few steps already land close to the data --
which is how the same model trades quality for speed at inference time.

Timesteps are drawn *per element*, not per batch.  A context frame sits at
``t = 1`` while the frame being generated is noisy, so one training run
covers autoregressive rollout, joint denoising and pure reconstruction.
"""

from __future__ import annotations

import torch
from torch import Tensor

__all__ = [
    "timestep_grid",
    "interpolate",
    "velocity_target",
    "sample_timesteps",
    "flow_loss",
    "euler_sample",
    "shift_timesteps",
]


def _broadcast_t(t: Tensor, like: Tensor) -> Tensor:
    """Reshape ``(B,)`` timesteps to broadcast against ``(B, ...)`` data."""
    if t.ndim != 1:
        raise ValueError(f"timesteps must be 1-D, got {tuple(t.shape)}")
    if t.shape[0] != like.shape[0]:
        raise ValueError(f"timestep batch {t.shape[0]} != data batch {like.shape[0]}")
    return t.reshape(-1, *([1] * (like.ndim - 1))).to(like.dtype)


def interpolate(x1: Tensor, noise: Tensor, t: Tensor) -> Tensor:
    """The rectified-flow interpolant ``(1 - t) * noise + t * x1``."""
    tb = _broadcast_t(t, x1)
    return (1.0 - tb) * noise + tb * x1


def velocity_target(x1: Tensor, noise: Tensor) -> Tensor:
    """Ground-truth velocity of the straight path: ``x1 - noise``."""
    return x1 - noise


def sample_timesteps(
    batch: int,
    *,
    device=None,
    dtype: torch.dtype = torch.float32,
    distribution: str = "logit_normal",
    mean: float = 0.0,
    std: float = 1.0,
    generator: torch.Generator | None = None,
) -> Tensor:
    """Draw training timesteps in ``[0, 1]``.

    ``logit_normal`` concentrates samples near ``t = 0.5`` where the velocity
    field is hardest to fit, and is the default used by modern rectified-flow
    image models; ``uniform`` is available for ablations.
    """
    if distribution == "uniform":
        return torch.rand(batch, device=device, dtype=dtype, generator=generator)
    if distribution == "logit_normal":
        normal = torch.randn(batch, device=device, dtype=dtype, generator=generator)
        return torch.sigmoid(normal * std + mean)
    raise ValueError(f"unknown timestep distribution {distribution!r}")


def shift_timesteps(t: Tensor, shift: float = 1.0) -> Tensor:
    """Resolution-aware timestep shift.

    Higher-resolution latents need proportionally more of the trajectory spent
    at high noise; ``shift > 1`` pushes ``t`` toward ``0`` to compensate.
    """
    if shift == 1.0:
        return t
    return shift * t / (1.0 + (shift - 1.0) * t)


def timestep_grid(
    steps: int, *, shift: float = 1.0, device=None, dtype: torch.dtype = torch.float32
) -> Tensor:
    """The ``steps + 1`` integration times from ``t = 0`` to ``t = 1``.

    Shared by every sampler so the schedule is defined once: a mismatch
    between the grid a sampler walks and the one the model was trained
    against shows up as quality loss with no error anywhere.
    """
    if steps < 1:
        raise ValueError("steps must be >= 1")
    return shift_timesteps(torch.linspace(0.0, 1.0, steps + 1, device=device, dtype=dtype), shift)


def flow_loss(pred_v: Tensor, x1: Tensor, noise: Tensor, weight: Tensor | None = None) -> Tensor:
    """Mean squared velocity error, optionally weighted per sample.

    ``weight`` is ``(B,)`` and is typically the "is a generation target" mask,
    so observed context elements contribute nothing to the gradient.
    """
    target = velocity_target(x1, noise)
    err = (pred_v.float() - target.float()).pow(2)
    err = err.flatten(1).mean(1)
    if weight is None:
        return err.mean()
    weight = weight.to(err.dtype)
    return (err * weight).sum() / weight.sum().clamp_min(1e-8)


@torch.no_grad()
def euler_sample(
    velocity_fn,
    shape: tuple[int, ...],
    *,
    steps: int = 32,
    device=None,
    dtype: torch.dtype = torch.float32,
    noise: Tensor | None = None,
    shift: float = 1.0,
    generator: torch.Generator | None = None,
) -> Tensor:
    """Integrate the learned velocity field from noise to data.

    ``velocity_fn(x_t, t)`` receives the current sample and a ``(B,)`` tensor
    of times and returns the predicted velocity.  Euler is sufficient here:
    on a rectified path the exact trajectory is a straight line, so error
    comes only from the model, not the integrator.
    """
    x = (
        torch.randn(shape, device=device, dtype=dtype, generator=generator)
        if noise is None
        else noise.to(device=device, dtype=dtype)
    )
    grid = timestep_grid(steps, shift=shift, device=device, dtype=dtype)

    for i in range(steps):
        t_now, t_next = grid[i], grid[i + 1]
        t_batch = t_now.expand(shape[0])
        v = velocity_fn(x, t_batch)
        x = x + (t_next - t_now) * v
    return x
