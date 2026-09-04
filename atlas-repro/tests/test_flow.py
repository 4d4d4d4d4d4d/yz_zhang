"""Rectified-flow tests."""

import pytest
import torch

from atlas.flow import (
    euler_sample,
    flow_loss,
    interpolate,
    sample_timesteps,
    shift_timesteps,
    velocity_target,
)


def test_interpolant_hits_the_endpoints():
    x1 = torch.randn(4, 3, 8, 8)
    noise = torch.randn_like(x1)
    assert torch.allclose(interpolate(x1, noise, torch.zeros(4)), noise, atol=1e-6)
    assert torch.allclose(interpolate(x1, noise, torch.ones(4)), x1, atol=1e-6)


def test_velocity_is_the_derivative_of_the_path():
    x1 = torch.randn(2, 3, 4, 4)
    noise = torch.randn_like(x1)
    t0, t1 = torch.full((2,), 0.3), torch.full((2,), 0.3 + 1e-3)
    numeric = (interpolate(x1, noise, t1) - interpolate(x1, noise, t0)) / 1e-3
    assert torch.allclose(numeric, velocity_target(x1, noise), atol=1e-3)


def test_perfect_velocity_integrates_back_to_the_data():
    """Euler on a straight path is exact -- one step should suffice."""
    x1 = torch.randn(3, 2, 4, 4)
    noise = torch.randn_like(x1)

    def velocity_fn(x, t):
        return velocity_target(x1, noise)

    out = euler_sample(velocity_fn, x1.shape, steps=1, noise=noise)
    assert torch.allclose(out, x1, atol=1e-5)


def test_timesteps_stay_in_range():
    for dist in ("uniform", "logit_normal"):
        t = sample_timesteps(512, distribution=dist)
        assert t.min() >= 0.0 and t.max() <= 1.0


def test_shift_is_monotone_and_fixes_the_endpoints():
    t = torch.linspace(0, 1, 32)
    shifted = shift_timesteps(t, 3.0)
    assert pytest.approx(0.0, abs=1e-6) == float(shifted[0])
    assert pytest.approx(1.0, abs=1e-6) == float(shifted[-1])
    assert bool((shifted.diff() > 0).all())
    # shift > 1 spends more of the trajectory at high noise
    assert bool((shifted[1:-1] >= t[1:-1]).all())


def test_loss_is_zero_for_a_perfect_prediction():
    x1 = torch.randn(4, 3, 4, 4)
    noise = torch.randn_like(x1)
    assert float(flow_loss(velocity_target(x1, noise), x1, noise)) == pytest.approx(0.0, abs=1e-9)


def test_loss_weight_masks_out_observed_elements():
    x1 = torch.randn(2, 3, 4, 4)
    noise = torch.randn_like(x1)
    pred = velocity_target(x1, noise).clone()
    pred[0] += 10.0  # a wildly wrong prediction on sample 0
    weight = torch.tensor([0.0, 1.0])
    assert float(flow_loss(pred, x1, noise, weight)) == pytest.approx(0.0, abs=1e-9)
