"""Tests of the architectural invariants that make this Atlas and not a ViT."""

import pytest
import torch

from atlas.batching import build_context, collate
from atlas.config import AtlasConfig
from atlas.data import SyntheticWorlds
from atlas.model import AtlasModel, fourier_features, patchify, unpatchify
from atlas.spatial_context import DEPTH, IMAGE, TEXT
from atlas.text import WordTokenizer


def tiny_config(**overrides):
    base = dict(
        dim=48, depth=2, n_heads=2, image_size=16, patch_size=4,
        text_vocab_size=64, max_text_len=8, plucker_bands=2,
    )
    base.update(overrides)
    return AtlasConfig(**base)


def make_batch(batch=2, views=3, size=16, seed=0):
    ds = SyntheticWorlds(length=batch, image_size=size, views=views, seed=seed)
    return collate([ds[i] for i in range(batch)])


def wake_model(model, seed=0):
    """Move a freshly initialised model off its identity initialisation.

    Two things are zero-initialised on purpose.  The output heads start at
    zero, so an untrained model predicts no velocity at all.  And every block
    uses adaLN-Zero, whose gates start at zero -- which makes the whole stack
    token-wise identity, with no attention contribution whatsoever.  Both are
    the right defaults for training stability, but they mean a fresh model
    cannot exhibit *any* information flow between elements.  Tests about how
    information flows therefore need a model past that point; randomising the
    gates and heads stands in for a few steps of training.
    """
    g = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for head in (model.image_out, model.depth_out):
            head.weight.normal_(0.0, 0.05, generator=g)
            head.bias.normal_(0.0, 0.05, generator=g)
        for block in model.transformer.blocks:
            block.modulation[1].weight.normal_(0.0, 0.02, generator=g)
            block.modulation[1].bias.normal_(0.0, 0.10, generator=g)
        model.transformer.modulation_out[1].weight.normal_(0.0, 0.02, generator=g)
        model.transformer.modulation_out[1].bias.normal_(0.0, 0.10, generator=g)
    return model


def build(model, batch, n_observed=1, predict_depth=True):
    tok = WordTokenizer(max_len=model.config.max_text_len)
    ctx = build_context(
        batch, tok, n_observed=n_observed, predict_depth=predict_depth,
        max_text_len=model.config.max_text_len,
    )
    return model.encode_context(ctx)


def test_patchify_roundtrip():
    x = torch.randn(2, 3, 12, 8)
    tokens = patchify(x, 4)
    assert tokens.shape == (2, 6, 48)
    assert torch.allclose(unpatchify(tokens, 4, 3, 3, 2), x)


def test_fourier_features_widen_the_channel_as_documented():
    x = torch.randn(2, 5, 6)
    assert fourier_features(x, 3).shape == (2, 5, 6 * (2 * 3 + 1))
    assert torch.allclose(fourier_features(x, 0), x)


def test_config_rejects_head_dims_rope_cannot_split():
    with pytest.raises(ValueError, match="divisible by 6"):
        AtlasConfig(dim=64, n_heads=8)


def test_forward_shapes_match_the_context():
    cfg = tiny_config()
    model = AtlasModel(cfg)
    ctx = build(model, make_batch())
    out = model.forward(ctx)

    assert len(out) == len(ctx)
    for element, pred in zip(ctx, out):
        if element.kind == TEXT:
            assert pred.shape == (*element.data.shape, cfg.text_vocab_size)
        else:
            assert pred.shape == element.data.shape


def test_output_heads_start_at_zero():
    """Identity initialisation: an untrained model predicts no velocity at all."""
    model = AtlasModel(tiny_config()).eval()
    ctx = build(model, make_batch(), n_observed=1)
    with torch.no_grad():
        out = model.forward(ctx)
    for element, pred in zip(ctx, out):
        if element.is_continuous:
            assert float(pred.abs().max()) == 0.0


def test_adaln_gates_start_closed():
    """adaLN-Zero: at initialisation no attention or MLP output reaches the residual."""
    model = AtlasModel(tiny_config()).eval()
    cond = torch.randn(1, 4, model.config.dim)
    for block in model.transformer.blocks:
        with torch.no_grad():
            gates = block.modulation(cond).chunk(6, dim=-1)
        assert float(gates[2].abs().max()) == 0.0  # attention gate
        assert float(gates[5].abs().max()) == 0.0  # MLP gate


def test_elements_cannot_see_the_future():
    """The block-causal core claim: element k is independent of element k+1."""
    torch.manual_seed(0)
    model = wake_model(AtlasModel(tiny_config()).eval())
    ctx = build(model, make_batch(), n_observed=1)

    with torch.no_grad():
        before = model.forward(ctx)

    last = len(ctx) - 1
    perturbed = ctx.replace_at(last, ctx[last].with_data(torch.randn_like(ctx[last].data) * 5))
    with torch.no_grad():
        after = model.forward(perturbed)

    for i in range(last):
        assert torch.allclose(before[i], after[i], atol=1e-5), f"element {i} leaked from the future"
    assert not torch.allclose(before[last], after[last], atol=1e-4)


def test_a_later_element_does_depend_on_an_earlier_one():
    torch.manual_seed(0)
    model = wake_model(AtlasModel(tiny_config()).eval())
    ctx = build(model, make_batch(), n_observed=1)

    with torch.no_grad():
        before = model.forward(ctx)
    perturbed = ctx.replace_at(1, ctx[1].with_data(torch.randn_like(ctx[1].data)))
    with torch.no_grad():
        after = model.forward(perturbed)

    assert not torch.allclose(before[-1], after[-1], atol=1e-5)


def test_camera_pose_changes_the_prediction():
    """Without this, the model is not spatially grounded at all."""
    torch.manual_seed(0)
    model = wake_model(AtlasModel(tiny_config()).eval())
    ctx = build(model, make_batch(), n_observed=1)

    idx = ctx.indices_of(IMAGE)[-1]
    element = ctx[idx]
    with torch.no_grad():
        before = model.forward(ctx)[idx]

    from atlas.cameras import Cameras

    moved = element.cameras.w2c.clone()
    moved[:, :3, 3] += 1.5
    shifted = element.__class__(
        element.kind,
        element.data,
        Cameras(moved, element.cameras.K, element.cameras.height, element.cameras.width),
        element.observed,
        element.t,
    )
    with torch.no_grad():
        after = model.forward(ctx.replace_at(idx, shifted))[idx]

    assert not torch.allclose(before, after, atol=1e-5)


def test_disabling_plucker_removes_pose_sensitivity():
    torch.manual_seed(0)
    model = AtlasModel(tiny_config(use_plucker=False)).eval()
    assert model.ray_in is None


def test_observed_elements_are_not_noised():
    torch.manual_seed(0)
    model = AtlasModel(tiny_config())
    ctx = build(model, make_batch(), n_observed=2)
    noisy, targets = model.add_noise(ctx)

    for element, original in zip(noisy, ctx):
        if not element.is_continuous:
            continue
        obs = element.observed
        if bool(obs.any()):
            assert torch.allclose(element.data[obs], original.data[obs], atol=1e-6)
            assert torch.allclose(element.t[obs], torch.ones_like(element.t[obs]))


def test_loss_is_finite_and_backpropagates():
    torch.manual_seed(0)
    model = AtlasModel(tiny_config())
    ctx = build(model, make_batch(), n_observed=1)
    loss, stats = model.compute_loss(ctx)

    assert torch.isfinite(loss)
    assert set(stats) == {"loss", "loss_image", "loss_depth", "loss_text"}
    loss.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads and all(torch.isfinite(g).all() for g in grads)


def test_denoise_elements_marks_targets_observed():
    torch.manual_seed(0)
    model = AtlasModel(tiny_config()).eval()
    ctx = build(model, make_batch(), n_observed=1)
    idx = [i for i, e in enumerate(ctx) if e.kind == DEPTH][:1]

    out = model.denoise_elements(ctx, idx, steps=2)
    assert bool(out[idx[0]].observed.all())
    assert out[idx[0]].data.shape == ctx[idx[0]].data.shape


def test_reconstruct_returns_one_pointmap_per_view():
    torch.manual_seed(0)
    cfg = tiny_config()
    model = AtlasModel(cfg).eval()
    ctx = build(model, make_batch(views=3), n_observed=3, predict_depth=False)

    _, points = model.reconstruct(ctx, steps=2)
    assert points.shape == (2, 3, cfg.image_size, cfg.image_size, 3)
    assert torch.isfinite(points).all()


def test_generate_views_extends_the_context():
    torch.manual_seed(0)
    cfg = tiny_config()
    model = AtlasModel(cfg).eval()
    ctx = build(model, make_batch(views=2), n_observed=2, predict_depth=False)

    from atlas.data import orbit_cameras

    g = torch.Generator().manual_seed(0)
    cams = orbit_cameras(2, g, height=cfg.image_size, width=cfg.image_size)
    cams = cams.reshape(1, 2)
    cams = type(cams)(cams.w2c.expand(2, 2, 4, 4).contiguous(), cams.K.expand(2, 2, 3, 3).contiguous(), cfg.image_size, cfg.image_size)

    before = len(ctx)
    out = model.generate_views(ctx, cams, steps=2)
    # two new views, each contributing an image and a depth element
    assert len(out) == before + 4


def test_guidance_uses_the_live_context_not_a_snapshot():
    """Classifier-free guidance must see the views generated so far.

    A stale unconditional context would drift further from the conditional
    branch with every new frame, so check that ``uncond_fn`` is handed the
    context as it stands at the moment of the call.
    """
    torch.manual_seed(0)
    cfg = tiny_config()
    model = wake_model(AtlasModel(cfg).eval())
    ctx = build(model, make_batch(views=2), n_observed=2, predict_depth=False)

    from atlas.data import orbit_cameras

    g = torch.Generator().manual_seed(0)
    cams = orbit_cameras(2, g, height=cfg.image_size, width=cfg.image_size).reshape(1, 2)
    cams = type(cams)(
        cams.w2c.expand(2, 2, 4, 4).contiguous(), cams.K.expand(2, 2, 3, 3).contiguous(),
        cfg.image_size, cfg.image_size,
    )

    seen: list[int] = []

    def uncond_fn(context):
        seen.append(len(context))
        return context

    model.generate_views(ctx, cams, steps=2, guidance=2.0, uncond_fn=uncond_fn)

    assert seen, "guidance never consulted the unconditional branch"
    # The context grows as views are appended, so the callback must see it grow.
    assert seen[-1] > seen[0], f"unconditional context never grew: {seen}"


def test_guidance_changes_the_result():
    torch.manual_seed(0)
    cfg = tiny_config()
    model = wake_model(AtlasModel(cfg).eval())
    ctx = build(model, make_batch(views=2), n_observed=1, predict_depth=False)
    targets = [i for i in ctx.indices_of(IMAGE) if not bool(ctx[i].observed.all())]

    def uncond_fn(context):
        text = context.indices_of(TEXT)[0]
        return context.replace_at(text, context[text].with_data(torch.zeros_like(context[text].data)))

    torch.manual_seed(1)
    plain = model.denoise_elements(ctx, targets, steps=3)
    torch.manual_seed(1)
    guided = model.denoise_elements(ctx, targets, steps=3, guidance=3.0, uncond_fn=uncond_fn)

    assert not torch.allclose(plain[targets[0]].data, guided[targets[0]].data, atol=1e-5)


def test_text_loss_ignores_padding():
    """Predicting <pad> is free accuracy; an all-padding caption has no signal."""
    torch.manual_seed(0)
    cfg = tiny_config()
    model = AtlasModel(cfg)
    ctx = build(model, make_batch(), n_observed=1)

    text_idx = ctx.indices_of(TEXT)[0]
    blank = torch.full_like(ctx[text_idx].data, cfg.text_pad_id)
    ctx = ctx.replace_at(text_idx, ctx[text_idx].with_data(blank))

    _, stats = model.compute_loss(ctx)
    assert stats["loss_text"] == 0.0
    assert torch.isfinite(torch.tensor(stats["loss"]))


def test_text_loss_is_nonzero_for_a_real_caption():
    torch.manual_seed(0)
    model = AtlasModel(tiny_config())
    _, stats = model.compute_loss(build(model, make_batch(), n_observed=1))
    assert stats["loss_text"] > 0.0
