"""Tests for the training plumbing: schedule, EMA, curriculum, tokenizer wiring."""

import pytest
import torch

from atlas.batching import build_context, collate
from atlas.config import AtlasConfig, TrainConfig, load_config
from atlas.data import SyntheticWorlds
from atlas.model import AtlasModel
from atlas.text import WordTokenizer
from atlas.tokenizer import ImageVAE, load_pretrained_vae
from atlas.train import EMA, build_optimizer, lr_at, train


def tiny_config(**overrides):
    base = dict(dim=48, depth=2, n_heads=2, image_size=16, patch_size=4,
                text_vocab_size=64, max_text_len=8, plucker_bands=2)
    base.update(overrides)
    return AtlasConfig(**base)


def test_shipped_configs_are_valid():
    for path in ("configs/tiny.json", "configs/small.json"):
        model_cfg, train_cfg = load_config(path)
        assert (model_cfg.dim // model_cfg.n_heads) % 6 == 0
        assert train_cfg.views_per_sample <= model_cfg.max_views


def test_small_config_requires_a_pretrained_tokenizer():
    """A "vae" config without a checkpoint would train on a random latent space."""
    model_cfg, train_cfg = load_config("configs/small.json")
    assert model_cfg.tokenizer == "vae"
    assert train_cfg.vae_checkpoint, "small.json must name a pretrained tokenizer"

    train_cfg.vae_checkpoint = None
    train_cfg.device = "cpu"
    with pytest.raises(ValueError, match="vae_checkpoint is unset"):
        train(model_cfg, train_cfg)


def test_vae_checkpoint_mismatch_is_rejected():
    vae = ImageVAE(latent_channels=4, downsample=4, base_channels=16)
    torch.save({"vae": vae.state_dict(), "downsample": 8, "latent_channels": 4}, "/tmp/atlas_vae_bad.pt")
    with pytest.raises(ValueError, match="downsample"):
        load_pretrained_vae("/tmp/atlas_vae_bad.pt", vae)


def test_vae_checkpoint_roundtrips():
    vae = ImageVAE(latent_channels=4, downsample=4, base_channels=16)
    torch.save(
        {"vae": vae.state_dict(), "downsample": 4, "latent_channels": 4, "scaling_factor": 2.5},
        "/tmp/atlas_vae_ok.pt",
    )
    fresh = ImageVAE(latent_channels=4, downsample=4, base_channels=16)
    load_pretrained_vae("/tmp/atlas_vae_ok.pt", fresh)
    assert fresh.scaling_factor == 2.5
    # encode() applies scaling_factor, which the checkpoint just changed to
    # 2.5, so compare the raw posterior means rather than the scaled latents.
    x = torch.rand(1, 3, 16, 16) * 2 - 1
    assert torch.allclose(vae.posterior(x).mean, fresh.posterior(x).mean, atol=1e-6)
    assert torch.allclose(fresh.encode(x), fresh.posterior(x).mean * 2.5, atol=1e-6)


def test_vae_roundtrip_shapes():
    vae = ImageVAE(latent_channels=4, downsample=4, base_channels=16)
    x = torch.rand(2, 3, 32, 32) * 2 - 1
    z = vae.encode(x)
    assert z.shape == (2, 4, 8, 8)
    assert vae.decode(z).shape == x.shape
    assert vae.latent_size(32, 32) == (8, 8)


def test_tokenizer_rejects_indivisible_sizes():
    vae = ImageVAE(downsample=4, base_channels=16)
    with pytest.raises(ValueError, match="divisible"):
        vae.latent_size(30, 32)


def test_build_context_enforces_max_views():
    ds = SyntheticWorlds(length=1, image_size=16, views=4, seed=0)
    batch = collate([ds[0]])
    tok = WordTokenizer(max_len=8)
    with pytest.raises(ValueError, match="allows 2"):
        build_context(batch, tok, n_observed=1, max_text_len=8, max_views=2)


def test_curriculum_endpoints_produce_valid_contexts():
    """n_observed = 0 is text-to-world; n_observed = V is pure reconstruction."""
    model = AtlasModel(tiny_config())
    ds = SyntheticWorlds(length=1, image_size=16, views=3, seed=0)
    batch = collate([ds[0]])
    tok = WordTokenizer(max_len=8)

    for n_observed in (0, 3):
        ctx = build_context(batch, tok, n_observed=n_observed, max_text_len=8)
        loss, _ = model.compute_loss(model.encode_context(ctx))
        assert torch.isfinite(loss)


def test_lr_schedule_warms_up_then_decays():
    cfg = TrainConfig(steps=1000, warmup_steps=100, lr=1e-3)
    assert lr_at(0, cfg) < cfg.lr
    assert lr_at(99, cfg) == pytest.approx(cfg.lr, rel=1e-6)
    assert lr_at(500, cfg) < cfg.lr
    assert lr_at(999, cfg) == pytest.approx(0.1 * cfg.lr, rel=0.05)


def test_optimizer_excludes_norms_and_biases_from_weight_decay():
    model = AtlasModel(tiny_config())
    opt = build_optimizer(model, TrainConfig(weight_decay=0.05))
    decayed, plain = opt.param_groups
    assert decayed["weight_decay"] == 0.05 and plain["weight_decay"] == 0.0
    assert all(p.ndim >= 2 for p in decayed["params"])
    assert all(p.ndim < 2 for p in plain["params"])


def test_train_rejects_more_views_than_the_model_allows():
    model_cfg = tiny_config(max_views=2)
    train_cfg = TrainConfig(views_per_sample=4, device="cpu")
    with pytest.raises(ValueError, match="exceeds"):
        train(model_cfg, train_cfg)


def test_ema_tracks_the_model():
    model = AtlasModel(tiny_config())
    ema = EMA(model, decay=0.5)
    with torch.no_grad():
        for p in model.parameters():
            p.add_(1.0)
    ema.update(model, step=1000)

    for shadow, live in zip(ema.shadow.parameters(), model.parameters()):
        assert not torch.allclose(shadow, live)  # it lags
        with torch.no_grad():
            assert float((shadow - live).abs().max()) < 1.0  # but it moved toward it


def test_reconstruction_mode_supervises_depth_only():
    """With every view observed there is no image target -- only depth is learned.

    This is the reconstruction end of the curriculum, and a zero image loss
    there is correct rather than a silently broken objective.
    """
    torch.manual_seed(0)
    model = AtlasModel(tiny_config())
    ds = SyntheticWorlds(length=1, image_size=16, views=2, seed=0)
    batch = collate([ds[0]])
    tok = WordTokenizer(max_len=8)

    ctx = model.encode_context(build_context(batch, tok, n_observed=2, max_text_len=8))
    _, stats = model.compute_loss(ctx)
    assert stats["loss_image"] == 0.0
    assert stats["loss_depth"] > 0.0

    ctx = model.encode_context(build_context(batch, tok, n_observed=1, max_text_len=8))
    _, stats = model.compute_loss(ctx)
    assert stats["loss_image"] > 0.0
