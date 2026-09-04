"""Training loop for the Atlas reproduction.

Run with::

    python -m atlas.train --config configs/tiny.json

The interesting part is the *curriculum*.  Each step draws how many leading
views are given as clean context.  Zero observed views is text-to-world
generation; one or two is novel-view synthesis; all of them is pure depth
reconstruction.  Because the number of observed views is just a property of
the spatial context -- not of the architecture -- a single set of weights
learns all three regimes at once.  That is the whole point of the omni model.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from copy import deepcopy
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from .batching import build_context, collate
from .config import AtlasConfig, TrainConfig, load_config
from .data import build_dataset
from .model import AtlasModel
from .text import WordTokenizer

__all__ = ["train", "EMA", "build_optimizer", "lr_at"]


class EMA:
    """Exponential moving average of model parameters."""

    def __init__(self, model: torch.nn.Module, decay: float = 0.999):
        self.decay = decay
        self.shadow = deepcopy(model).eval()
        for p in self.shadow.parameters():
            p.requires_grad_(False)

    @torch.no_grad()
    def update(self, model: torch.nn.Module, step: int) -> None:
        # Warm up the decay so the average is not dominated by the random init.
        d = min(self.decay, (1.0 + step) / (10.0 + step))
        for s, p in zip(self.shadow.parameters(), model.parameters()):
            s.lerp_(p.detach(), 1.0 - d)
        for s, p in zip(self.shadow.buffers(), model.buffers()):
            s.copy_(p)

    def state_dict(self):
        return self.shadow.state_dict()


def build_optimizer(model: torch.nn.Module, cfg: TrainConfig) -> torch.optim.Optimizer:
    """AdamW with weight decay only on matrices, never on norms or biases."""
    decay, no_decay = [], []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        (decay if param.ndim >= 2 else no_decay).append(param)
    groups = [
        {"params": decay, "weight_decay": cfg.weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]
    return torch.optim.AdamW(groups, lr=cfg.lr, betas=tuple(cfg.betas))


def lr_at(step: int, cfg: TrainConfig) -> float:
    """Linear warmup then cosine decay to a tenth of the peak."""
    if step < cfg.warmup_steps:
        return cfg.lr * (step + 1) / max(1, cfg.warmup_steps)
    progress = (step - cfg.warmup_steps) / max(1, cfg.steps - cfg.warmup_steps)
    progress = min(1.0, max(0.0, progress))
    return cfg.lr * (0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * progress)))


def _infinite(loader: DataLoader):
    while True:
        yield from loader


def train(model_cfg: AtlasConfig, train_cfg: TrainConfig) -> Path:
    # Validate the configuration before touching a device or allocating a
    # model, so a misconfigured run fails on the config rather than on CUDA.
    if model_cfg.tokenizer == "vae" and not train_cfg.vae_checkpoint:
        raise ValueError(
            'model.tokenizer is "vae" but train.vae_checkpoint is unset -- '
            "pretrain one with `python -m atlas.train_vae` and point at its vae.pt"
        )
    if train_cfg.views_per_sample > model_cfg.max_views:
        raise ValueError(
            f"train.views_per_sample ({train_cfg.views_per_sample}) exceeds "
            f"model.max_views ({model_cfg.max_views})"
        )

    torch.manual_seed(train_cfg.seed)
    device = torch.device(train_cfg.device)
    out_dir = Path(train_cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    text_tokenizer = WordTokenizer(max_len=model_cfg.max_text_len)
    if text_tokenizer.vocab_size > model_cfg.text_vocab_size:
        raise ValueError(
            f"caption vocabulary has {text_tokenizer.vocab_size} words but the model "
            f"was configured for {model_cfg.text_vocab_size}"
        )

    dataset = build_dataset(
        train_cfg.dataset,
        length=train_cfg.scenes,
        image_size=model_cfg.image_size,
        views=train_cfg.views_per_sample,
        seed=train_cfg.seed,
        **({"root": train_cfg.data_root} if train_cfg.dataset == "posed" else {}),
    )
    loader = DataLoader(
        dataset,
        batch_size=train_cfg.batch_size,
        shuffle=True,
        num_workers=train_cfg.num_workers,
        collate_fn=collate,
        drop_last=True,
    )

    model = AtlasModel(model_cfg).to(device)

    if model_cfg.tokenizer == "vae":
        # The latent tokenizer is pretrained by atlas.train_vae and frozen here.
        # Training the flow against a randomly initialised latent space would
        # look like it was working while learning nothing transferable.
        from .tokenizer import load_pretrained_vae

        load_pretrained_vae(train_cfg.vae_checkpoint, model.tokenizer)
        model.tokenizer.to(device)
        for param in model.tokenizer.parameters():
            param.requires_grad_(False)
        model.tokenizer.eval()
        print(f"loaded frozen tokenizer from {train_cfg.vae_checkpoint}")

    n_params = sum(p.numel() for p in model.parameters())
    print(f"model: {n_params / 1e6:.2f}M parameters, {model_cfg.tokens_per_view} tokens per view")

    optimizer = build_optimizer(model, train_cfg)
    ema = EMA(model, train_cfg.ema_decay)
    (out_dir / "config.json").write_text(
        json.dumps({"model": model_cfg.to_dict(), "train": vars(train_cfg)}, indent=2, default=str)
    )

    log_path = out_dir / "log.jsonl"
    stream = _infinite(loader)
    running: dict[str, float] = {}
    start = time.time()

    for step in range(train_cfg.steps):
        for group in optimizer.param_groups:
            group["lr"] = lr_at(step, train_cfg)

        batch = next(stream)
        # The curriculum: how much of the world is given, versus generated.
        n_observed = int(
            torch.randint(
                train_cfg.min_observed_views, train_cfg.views_per_sample + 1, (1,)
            )
        )
        context = build_context(
            batch,
            text_tokenizer,
            n_observed=n_observed,
            predict_depth=model_cfg.predict_depth,
            max_text_len=model_cfg.max_text_len,
            max_views=model_cfg.max_views,
            device=device,
        )
        latent_context = model.encode_context(context)

        loss, stats = model.compute_loss(
            latent_context,
            depth_weight=train_cfg.depth_loss_weight,
            text_weight=train_cfg.text_loss_weight,
            distribution=train_cfg.timestep_distribution,
            shift=train_cfg.timestep_shift,
        )

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), train_cfg.grad_clip)
        optimizer.step()
        ema.update(model, step)

        stats["grad_norm"] = float(grad_norm)
        stats["n_observed"] = n_observed
        for k, v in stats.items():
            running[k] = running.get(k, 0.0) + float(v)

        if (step + 1) % train_cfg.log_every == 0:
            avg = {k: v / train_cfg.log_every for k, v in running.items()}
            running.clear()
            elapsed = time.time() - start
            record = {"step": step + 1, "lr": lr_at(step, train_cfg), "sec": round(elapsed, 1), **avg}
            print(
                f"step {step + 1:>6}/{train_cfg.steps}  loss {avg['loss']:.4f}  "
                f"img {avg['loss_image']:.4f}  depth {avg['loss_depth']:.4f}  "
                f"text {avg['loss_text']:.4f}  ({elapsed:.0f}s)"
            )
            with log_path.open("a") as f:
                f.write(json.dumps(record) + "\n")

        if (step + 1) % train_cfg.ckpt_every == 0 or step + 1 == train_cfg.steps:
            ckpt = {
                "step": step + 1,
                "model": model.state_dict(),
                "ema": ema.state_dict(),
                "config": model_cfg.to_dict(),
            }
            torch.save(ckpt, out_dir / "checkpoint.pt")

    print(f"done in {time.time() - start:.0f}s -> {out_dir / 'checkpoint.pt'}")
    return out_dir / "checkpoint.pt"


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Atlas reproduction")
    parser.add_argument("--config", type=str, default=None, help="path to a JSON config")
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--device", type=str, default=None)
    parser.add_argument("--out-dir", type=str, default=None)
    parser.add_argument("--scenes", type=int, default=None)
    parser.add_argument("--num-workers", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.config:
        model_cfg, train_cfg = load_config(args.config)
    else:
        model_cfg, train_cfg = AtlasConfig(), TrainConfig()

    for name in ("steps", "batch_size", "device", "out_dir", "scenes", "num_workers", "seed"):
        value = getattr(args, name)
        if value is not None:
            setattr(train_cfg, name, value)

    train(model_cfg, train_cfg)


if __name__ == "__main__":
    main()
