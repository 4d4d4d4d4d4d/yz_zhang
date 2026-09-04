"""Pretrain the latent tokenizer.

At 32px pixels are cheap enough to diffuse directly (``tokenizer: identity``).
Above that the transformer needs a compressed latent, and that tokenizer has
to be trained first -- exactly the two-stage recipe every latent diffusion
system uses:

    python -m atlas.train_vae --steps 20000 --image-size 64 --downsample 4 \
        --out runs/vae-f4

Then point a model config at the result with ``"tokenizer": "vae"`` and set
``vae_scaling_factor`` to the value this script reports, which normalises the
latent to roughly unit variance so the flow sees a well-conditioned target.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from .batching import collate
from .data import SyntheticWorlds
from .tokenizer import ImageVAE

__all__ = ["train_vae"]


def train_vae(
    *,
    steps: int = 20_000,
    image_size: int = 64,
    downsample: int = 4,
    latent_channels: int = 4,
    base_channels: int = 64,
    batch_size: int = 16,
    lr: float = 1e-4,
    kl_weight: float = 1e-6,
    views: int = 2,
    scenes: int = 8192,
    device: str = "cpu",
    seed: int = 0,
    log_every: int = 100,
    out_dir: str = "runs/vae",
) -> Path:
    torch.manual_seed(seed)
    dev = torch.device(device)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dataset = SyntheticWorlds(length=scenes, image_size=image_size, views=views, seed=seed)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=collate, drop_last=True)

    vae = ImageVAE(
        latent_channels=latent_channels, base_channels=base_channels, downsample=downsample
    ).to(dev)
    opt = torch.optim.AdamW(vae.parameters(), lr=lr, betas=(0.9, 0.95))
    print(f"vae: {sum(p.numel() for p in vae.parameters()) / 1e6:.2f}M parameters, f{downsample}")

    def batches():
        while True:
            yield from loader

    stream = batches()
    start = time.time()
    running = {"rec": 0.0, "kl": 0.0}
    latent_sq = 0.0
    latent_n = 0

    for step in range(steps):
        batch = next(stream)
        # Every view is an independent image as far as the tokenizer cares.
        x = batch["image"].flatten(0, 1).to(dev)

        recon, posterior = vae(x)
        rec_loss = F.l1_loss(recon, x)
        kl_loss = posterior.kl().mean() / x[0].numel()
        loss = rec_loss + kl_weight * kl_loss

        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(vae.parameters(), 1.0)
        opt.step()

        running["rec"] += float(rec_loss)
        running["kl"] += float(kl_loss)
        with torch.no_grad():
            latent_sq += float(posterior.mean.pow(2).mean())
            latent_n += 1

        if (step + 1) % log_every == 0:
            print(
                f"step {step + 1:>6}/{steps}  l1 {running['rec'] / log_every:.4f}  "
                f"kl {running['kl'] / log_every:.4f}  ({time.time() - start:.0f}s)"
            )
            running = {"rec": 0.0, "kl": 0.0}

    # A scaling factor of 1/std keeps the latent at roughly unit variance.
    std = (latent_sq / max(1, latent_n)) ** 0.5
    scaling_factor = 1.0 / max(std, 1e-6)
    torch.save(
        {
            "vae": vae.state_dict(),
            "downsample": downsample,
            "latent_channels": latent_channels,
            "base_channels": base_channels,
            "scaling_factor": scaling_factor,
        },
        out / "vae.pt",
    )
    (out / "vae.json").write_text(
        json.dumps(
            {"downsample": downsample, "latent_channels": latent_channels, "scaling_factor": scaling_factor},
            indent=2,
        )
    )
    print(f"latent std {std:.4f} -> set vae_scaling_factor to {scaling_factor:.4f}")
    print(f"saved -> {out / 'vae.pt'}")
    return out / "vae.pt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Pretrain the Atlas latent tokenizer")
    parser.add_argument("--steps", type=int, default=20_000)
    parser.add_argument("--image-size", type=int, default=64)
    parser.add_argument("--downsample", type=int, default=4)
    parser.add_argument("--latent-channels", type=int, default=4)
    parser.add_argument("--base-channels", type=int, default=64)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--kl-weight", type=float, default=1e-6)
    parser.add_argument("--scenes", type=int, default=8192)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=str, default="runs/vae")
    args = parser.parse_args()

    train_vae(
        steps=args.steps, image_size=args.image_size, downsample=args.downsample,
        latent_channels=args.latent_channels, base_channels=args.base_channels,
        batch_size=args.batch_size, lr=args.lr, kl_weight=args.kl_weight,
        scenes=args.scenes, device=args.device, seed=args.seed, out_dir=args.out,
    )


if __name__ == "__main__":
    main()
