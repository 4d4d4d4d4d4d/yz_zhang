"""Reconstruct 3D from posed images.

    python -m atlas.reconstruct --ckpt runs/atlas-tiny/checkpoint.pt --scene 3

This is the mode where the images are *given* and only the depth elements are
noise.  Nothing about the model changes -- it is the same forward pass as
generation, with a different set of elements marked observed.  Because the
predicted depth lives in the same spatial context as the images, unprojecting
it fuses every view into one point cloud with no alignment step.

Writes a depth comparison against ground truth, the fused point cloud, and a
Gaussian splat.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from .batching import build_context, collate
from .data import SyntheticWorlds
from .depth_repr import decode_depth
from .export import points_from_context, write_gaussian_splat_ply, write_point_cloud_ply
from .imageio import colorize_depth, save_grid
from .metrics import pointmap_metrics
from .sample import load_checkpoint
from .spatial_context import DEPTH, IMAGE
from .text import WordTokenizer

__all__ = ["reconstruct_scene"]


@torch.no_grad()
def reconstruct_scene(
    model,
    *,
    scene: int = 0,
    views: int = 4,
    steps: int = 48,
    seed: int = 1234,
    device: str = "cpu",
) -> dict:
    """Predict depth for every view of a held-out scene."""
    cfg = model.config
    dev = torch.device(device)
    tokenizer = WordTokenizer(max_len=cfg.max_text_len)

    dataset = SyntheticWorlds(length=scene + 1, image_size=cfg.image_size, views=views, seed=seed)
    batch = collate([dataset[scene]])

    ctx = build_context(
        batch, tokenizer, n_observed=views, predict_depth=False,
        max_text_len=cfg.max_text_len, device=dev,
    )
    ctx = model.encode_context(ctx)
    work, points = model.reconstruct(ctx, steps=steps)

    depths = torch.stack(
        [decode_depth(work[i].data[:, 0])[0] for i in work.indices_of(DEPTH)]
    )
    images = torch.stack([model.decode_image(work[i].data)[0] for i in ctx.indices_of(IMAGE)])

    gt_depth = batch["depth"][0].to(dev)
    valid = batch["depth_valid"][0].to(dev)
    return {
        "caption": batch["caption"][0],
        "images": images,
        "depth": depths,
        "gt_depth": gt_depth,
        "valid": valid,
        "points": points[0],
        "metrics": pointmap_metrics(depths, gt_depth, valid),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct 3D from posed images")
    parser.add_argument("--ckpt", type=str, required=True)
    parser.add_argument("--scene", type=int, default=0)
    parser.add_argument("--views", type=int, default=4)
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--out", type=str, default="samples/reconstruct")
    args = parser.parse_args()

    model = load_checkpoint(args.ckpt, args.device)
    result = reconstruct_scene(
        model, scene=args.scene, views=args.views, steps=args.steps,
        seed=args.seed, device=args.device,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f'caption: "{result["caption"]}"')
    for key, value in result["metrics"].items():
        print(f"{key:>14}: {value:.4f}")

    # Rows: the input views, the predicted depth, the true depth.
    rows = [result["images"]]
    rows.append(torch.stack([colorize_depth(d).expand(3, -1, -1) for d in result["depth"]]))
    rows.append(
        torch.stack(
            [colorize_depth(d, v).expand(3, -1, -1) for d, v in zip(result["gt_depth"], result["valid"])]
        )
    )
    save_grid(out / "comparison.png", torch.cat(rows), columns=len(result["images"]))

    pts, rgb = points_from_context(
        result["points"], result["images"], depth=result["depth"], max_depth=12.0
    )
    write_point_cloud_ply(out / "scene.ply", pts, rgb)
    write_gaussian_splat_ply(out / "scene_splat.ply", pts, rgb, scale=0.02)
    print(f"wrote {pts.shape[0]} points -> {out}")


if __name__ == "__main__":
    main()
