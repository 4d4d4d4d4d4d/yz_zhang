"""Tests for the evaluation harness."""

import pytest
import torch

from atlas.config import AtlasConfig
from atlas.eval import evaluate
from atlas.model import AtlasModel


def tiny_model():
    torch.manual_seed(0)
    return AtlasModel(
        AtlasConfig(dim=48, depth=2, n_heads=2, image_size=16, patch_size=4,
                    text_vocab_size=64, max_text_len=8, plucker_bands=2)
    ).eval()


def test_evaluate_reports_metrics_next_to_their_baselines():
    metrics = evaluate(tiny_model(), scenes=2, views=2, observed=1, steps=2, batch_size=2)
    for key in ("recon/abs_rel", "recon/abs_rel_const", "nvs/psnr", "nvs/psnr_copy"):
        assert key in metrics, f"missing {key}"
        assert torch.isfinite(torch.tensor(metrics[key])), f"{key} is not finite"
    assert metrics["scenes"] == 2
    assert 0.0 <= metrics["recon/delta_1.25"] <= 1.0


def test_constant_depth_baseline_is_a_real_bound():
    """Scale alignment means the constant's value cannot matter."""
    from atlas.metrics import abs_rel

    target = torch.rand(4, 8, 8) + 0.5
    a = abs_rel(torch.ones_like(target), target)
    b = abs_rel(torch.full_like(target, 17.0), target)
    assert torch.allclose(a, b, atol=1e-5)
    assert float(a.mean()) > 0.0  # a constant is not a free win


def test_evaluate_needs_an_observed_view():
    with pytest.raises(ValueError, match="at least one observed view"):
        evaluate(tiny_model(), scenes=1, views=2, observed=0, steps=1, batch_size=1)


def test_evaluation_scenes_are_disjoint_from_training():
    """The eval seed must not collide with the training seed."""
    from atlas.config import TrainConfig
    from atlas.data import SyntheticWorlds
    import inspect

    default_eval_seed = inspect.signature(evaluate).parameters["seed"].default
    assert default_eval_seed != TrainConfig().seed

    train_scene = SyntheticWorlds(length=1, image_size=16, views=2, seed=TrainConfig().seed)[0]
    eval_scene = SyntheticWorlds(length=1, image_size=16, views=2, seed=default_eval_seed)[0]
    assert not torch.equal(train_scene["image"], eval_scene["image"])
