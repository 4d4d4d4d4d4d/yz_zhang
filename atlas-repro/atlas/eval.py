"""Evaluate a checkpoint on the three Atlas tasks.

    python -m atlas.eval --ckpt runs/atlas-tiny/checkpoint.pt --scenes 32

Reports:

``recon/*``   depth accuracy on views the model can see -- the 3D
              reconstruction protocol (scale-aligned absolute relative error
              and delta thresholds), as used on DTU / ETH3D / ScanNet.
``nvs/*``     PSNR of views generated at held-out poses, against the true
              render -- camera-controlled generation.

Both run through exactly the same model and the same spatial context; only
which elements are observed differs.

Each metric is reported next to a trivial baseline, because an absolute
error rate says nothing on its own:

``recon/abs_rel_const``  the best possible *constant* depth map.  Since the
                         metric is scale-aligned, this is what you score by
                         predicting no geometry at all -- only a model that
                         beats it has learned any shape.
``nvs/psnr_copy``        the nearest observed view copied to the target pose.
                         Beating it means the model moved the camera rather
                         than echoing what it was given.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from .batching import build_context, collate
from .data import SyntheticWorlds
from .depth_repr import decode_depth
from .metrics import pointmap_metrics, psnr
from .sample import load_checkpoint
from .spatial_context import DEPTH, IMAGE, SpatialContext
from .text import WordTokenizer

__all__ = ["evaluate"]


@torch.no_grad()
def evaluate(
    model,
    *,
    scenes: int = 32,
    views: int = 4,
    observed: int = 2,
    steps: int = 32,
    batch_size: int = 4,
    seed: int = 1234,
    device: str = "cpu",
) -> dict[str, float]:
    """Score reconstruction and novel-view synthesis on held-out scenes."""
    if observed < 1:
        raise ValueError("evaluation needs at least one observed view to condition on")

    cfg = model.config
    dev = torch.device(device)
    tokenizer = WordTokenizer(max_len=cfg.max_text_len)
    # A distinct seed offset guarantees these scenes were never trained on.
    dataset = SyntheticWorlds(length=scenes, image_size=cfg.image_size, views=views, seed=seed)

    recon: list[dict[str, float]] = []
    recon_const: list[dict[str, float]] = []
    nvs: list[float] = []
    nvs_copy: list[float] = []

    for start in range(0, scenes, batch_size):
        items = [dataset[i] for i in range(start, min(start + batch_size, scenes))]
        batch = collate(items)

        # -- 3D reconstruction: all views observed, depth is the unknown --
        ctx = build_context(
            batch, tokenizer, n_observed=views, predict_depth=False,
            max_text_len=cfg.max_text_len, device=dev,
        )
        ctx = model.encode_context(ctx)
        _, points = model.reconstruct(ctx, steps=steps)

        pred_depth = []
        for view in range(views):
            cam = ctx[ctx.indices_of(IMAGE)[view]].cameras
            fwd = cam.c2w[:, :3, 2]
            rel = points[:, view] - cam.centers[:, None, None, :]
            pred_depth.append((rel * fwd[:, None, None, :]).sum(-1))
        pred_depth = torch.stack(pred_depth, dim=1)

        gt_depth = batch["depth"].to(dev)
        valid = batch["depth_valid"].to(dev)
        recon.append(
            pointmap_metrics(pred_depth.flatten(0, 1), gt_depth.flatten(0, 1), valid.flatten(0, 1))
        )
        # Baseline: a constant depth map.  The metric aligns scale, so the
        # constant itself is irrelevant -- this is the score for predicting
        # no geometry whatsoever.
        recon_const.append(
            pointmap_metrics(
                torch.ones_like(pred_depth).flatten(0, 1),
                gt_depth.flatten(0, 1),
                valid.flatten(0, 1),
            )
        )

        # -- novel-view synthesis: a few views given, the rest generated --
        ctx = build_context(
            batch, tokenizer, n_observed=observed, predict_depth=False,
            max_text_len=cfg.max_text_len, device=dev,
        )
        ctx = model.encode_context(ctx)
        target_indices = [
            i for i in ctx.indices_of(IMAGE) if not bool(ctx[i].observed.all())
        ]
        generated = model.denoise_elements(ctx, target_indices, steps=steps)

        for i in target_indices:
            pred = model.decode_image(generated[i].data)
            view = ctx.indices_of(IMAGE).index(i)
            truth = batch["image"][:, view].to(dev)
            nvs.extend(psnr(pred, truth).tolist())
            # Baseline: copy the last observed view to this pose.
            nvs_copy.extend(psnr(batch["image"][:, observed - 1].to(dev), truth).tolist())

    def mean(rows, key):
        return float(sum(r[key] for r in rows) / len(rows))

    out = {f"recon/{k}": mean(recon, k) for k in recon[0]}
    out["recon/abs_rel_const"] = mean(recon_const, "abs_rel")
    out["nvs/psnr"] = float(sum(nvs) / len(nvs)) if nvs else float("nan")
    out["nvs/psnr_copy"] = float(sum(nvs_copy) / len(nvs_copy)) if nvs_copy else float("nan")
    out["scenes"] = scenes
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate an Atlas checkpoint")
    parser.add_argument("--ckpt", type=str, required=True)
    parser.add_argument("--scenes", type=int, default=32)
    parser.add_argument("--views", type=int, default=4)
    parser.add_argument("--observed", type=int, default=2)
    parser.add_argument("--steps", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    model = load_checkpoint(args.ckpt, args.device)
    metrics = evaluate(
        model,
        scenes=args.scenes,
        views=args.views,
        observed=args.observed,
        steps=args.steps,
        batch_size=args.batch_size,
        seed=args.seed,
        device=args.device,
    )
    for key, value in metrics.items():
        print(f"{key:>18}: {value:.4f}" if isinstance(value, float) else f"{key:>18}: {value}")
    if args.out:
        Path(args.out).write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
