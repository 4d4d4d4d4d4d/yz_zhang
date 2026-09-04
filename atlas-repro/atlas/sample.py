"""Generate worlds from a trained checkpoint.

    # text -> world, then fly a camera through it
    python -m atlas.sample --ckpt runs/atlas-tiny/checkpoint.pt \
        --prompt "a scene with two red spheres and one blue cube on the floor" \
        --views 8 --out samples/text2world

    # image -> world: condition on a real view from the dataset
    python -m atlas.sample --ckpt runs/atlas-tiny/checkpoint.pt --scene 7 --observed 1

Every generated view is denoised conditioned on the views generated before it,
so a trajectory stays consistent with itself; and because each view carries a
depth element, the same rollout also yields a fused point cloud and a Gaussian
splat with no extra reconstruction step.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch

from .batching import build_context, collate, null_text_context
from .cameras import Cameras, unproject_depth
from .config import AtlasConfig
from .data import SyntheticWorlds, orbit_cameras
from .depth_repr import decode_depth
from .export import points_from_context, write_gaussian_splat_ply, write_point_cloud_ply
from .imageio import colorize_depth, save_grid, save_png
from .model import AtlasModel
from .spatial_context import DEPTH, IMAGE, TEXT, Element, SpatialContext
from .text import WordTokenizer

__all__ = ["load_checkpoint", "generate"]


def load_checkpoint(path: str | Path, device: str = "cpu", use_ema: bool = True) -> AtlasModel:
    """Rebuild a model from a training checkpoint."""
    ckpt = torch.load(path, map_location=device, weights_only=False)
    cfg = AtlasConfig(**ckpt["config"])
    model = AtlasModel(cfg).to(device)
    state = ckpt["ema"] if use_ema and "ema" in ckpt else ckpt["model"]
    model.load_state_dict(state)
    model.eval()
    return model


def _trajectory(n_views: int, image_size: int, seed: int, device) -> Cameras:
    g = torch.Generator().manual_seed(seed)
    cams = orbit_cameras(n_views, g, height=image_size, width=image_size)
    return cams.to(device)


@torch.no_grad()
def generate(
    model: AtlasModel,
    *,
    prompt: str,
    n_views: int = 6,
    observed: int = 0,
    scene: int | None = None,
    steps: int = 48,
    guidance: float = 1.0,
    seed: int = 0,
    device: str = "cpu",
) -> dict:
    """Roll out ``n_views`` views, optionally conditioned on real observations."""
    cfg = model.config
    tokenizer = WordTokenizer(max_len=cfg.max_text_len)
    torch.manual_seed(seed)
    dev = torch.device(device)

    if scene is not None:
        # Condition on genuine posed views from a held-out scene.
        ds = SyntheticWorlds(
            length=scene + 1, image_size=cfg.image_size, views=max(observed, 1), seed=seed + 9_000
        )
        batch = collate([ds[scene]])
        context = build_context(
            batch, tokenizer, n_observed=observed, predict_depth=False,
            max_text_len=cfg.max_text_len, device=dev,
        )
        # Drop the unobserved views: they are what we are about to generate.
        keep = [context[0]] + [
            e for e in context if e.kind == IMAGE and bool(e.observed.all())
        ]
        context = SpatialContext(keep)
        context = model.encode_context(context)
        caption = batch["caption"][0]
    else:
        ids = tokenizer.encode_batch([prompt], cfg.max_text_len).to(dev)
        observed_flag = torch.ones(1, dtype=torch.bool, device=dev)
        context = SpatialContext([Element(TEXT, ids, observed=observed_flag)])
        caption = prompt

    uncond = null_text_context(context, tokenizer) if guidance != 1.0 else None
    cams = _trajectory(n_views, cfg.image_size, seed, dev)
    cams = cams.reshape(1, n_views) if cams.batch_shape == (n_views,) else cams

    context = model.generate_views(
        context, cams, steps=steps, with_depth=cfg.predict_depth,
        guidance=guidance, uncond_context=uncond,
    )

    # Walk the context pairing each view with the depth element that follows
    # it.  A view supplied as conditioning has no depth of its own, so the
    # geometry lists stay shorter than the image list -- keep them aligned by
    # recording, per view, whether depth was generated for it.
    images: list[torch.Tensor] = []
    geo_images: list[torch.Tensor] = []
    depths: list[torch.Tensor] = []
    points: list[torch.Tensor] = []

    for element in context:
        if element.kind == IMAGE:
            images.append(model.decode_image(element.data)[0])
        elif element.kind == DEPTH:
            if not images:
                raise RuntimeError("depth element appeared before any image element")
            metric = decode_depth(element.data[:, 0])
            depths.append(metric[0])
            points.append(unproject_depth(element.cameras, metric)[0])
            geo_images.append(images[-1])

    empty = torch.empty(0)
    return {
        "caption": caption,
        "images": torch.stack(images) if images else empty,
        "geometry_images": torch.stack(geo_images) if geo_images else empty,
        "depths": torch.stack(depths) if depths else empty,
        "points": torch.stack(points) if points else empty,
        "cameras": cams,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sample worlds from a trained Atlas model")
    parser.add_argument("--ckpt", type=str, required=True)
    parser.add_argument("--prompt", type=str, default="a scene with two red spheres and one blue cube on the floor")
    parser.add_argument("--views", type=int, default=6)
    parser.add_argument("--observed", type=int, default=0, help="number of real views to condition on")
    parser.add_argument("--scene", type=int, default=None, help="held-out scene index to condition on")
    parser.add_argument("--steps", type=int, default=48)
    parser.add_argument("--guidance", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--out", type=str, default="samples")
    parser.add_argument("--no-ema", action="store_true")
    args = parser.parse_args()

    model = load_checkpoint(args.ckpt, args.device, use_ema=not args.no_ema)
    result = generate(
        model,
        prompt=args.prompt,
        n_views=args.views,
        observed=args.observed,
        scene=args.scene,
        steps=args.steps,
        guidance=args.guidance,
        seed=args.seed,
        device=args.device,
    )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f'caption: "{result["caption"]}"')

    save_grid(out / "views.png", result["images"], columns=min(4, len(result["images"])))
    for i, img in enumerate(result["images"]):
        save_png(out / f"view_{i:02d}.png", img)

    if result["depths"].numel():
        save_grid(
            out / "depth.png",
            torch.stack([colorize_depth(d).expand(3, -1, -1) for d in result["depths"]]),
            columns=min(4, len(result["depths"])),
        )
        pts, rgb = points_from_context(
            result["points"], result["geometry_images"], depth=result["depths"], max_depth=12.0
        )
        write_point_cloud_ply(out / "world.ply", pts, rgb)
        write_gaussian_splat_ply(out / "world_splat.ply", pts, rgb, scale=0.02)
        print(f"wrote {pts.shape[0]} points -> {out / 'world.ply'}, {out / 'world_splat.ply'}")

    print(f"wrote {len(result['images'])} views -> {out}")


if __name__ == "__main__":
    main()
