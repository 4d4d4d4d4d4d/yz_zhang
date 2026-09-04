"""Configuration objects for the Atlas reproduction."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

__all__ = ["AtlasConfig", "TrainConfig", "load_config"]


@dataclass
class AtlasConfig:
    """Architecture of the omni model."""

    # -- backbone --
    dim: int = 384
    depth: int = 12
    n_heads: int = 6
    hidden_mult: float = 4.0

    # -- visual tokenisation --
    image_size: int = 64
    patch_size: int = 4
    tokenizer: str = "identity"          # "identity" | "vae"
    latent_channels: int = 3
    vae_downsample: int = 1
    vae_base_channels: int = 64
    vae_scaling_factor: float = 1.0

    # -- spatial grounding --
    plucker_bands: int = 8               # Fourier bands for the ray embedding
    use_plucker: bool = True

    # -- text --
    text_vocab_size: int = 512
    max_text_len: int = 32

    # -- context --
    max_views: int = 8
    predict_depth: bool = True

    def __post_init__(self) -> None:
        if self.dim % self.n_heads:
            raise ValueError(f"dim {self.dim} must be divisible by n_heads {self.n_heads}")
        head_dim = self.dim // self.n_heads
        if head_dim % 6:
            raise ValueError(
                f"head_dim {head_dim} must be divisible by 6 for 3-axis rotary embeddings"
            )
        if self.tokenizer == "identity" and self.vae_downsample != 1:
            raise ValueError("the identity tokenizer cannot downsample")
        if self.tokenizer == "identity" and self.latent_channels != 3:
            raise ValueError("the identity tokenizer emits 3 latent channels (RGB)")
        if self.image_size % (self.vae_downsample * self.patch_size):
            raise ValueError(
                f"image_size {self.image_size} must be divisible by "
                f"vae_downsample * patch_size ({self.vae_downsample * self.patch_size})"
            )

    # -- derived sizes ---------------------------------------------------
    @property
    def latent_size(self) -> int:
        return self.image_size // self.vae_downsample

    @property
    def token_grid(self) -> int:
        return self.latent_size // self.patch_size

    @property
    def tokens_per_view(self) -> int:
        return self.token_grid ** 2

    @property
    def depth_patch_size(self) -> int:
        """Depth stays in pixel space, so its patches cover the same footprint."""
        return self.patch_size * self.vae_downsample

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrainConfig:
    """Optimisation and data settings."""

    steps: int = 2000
    batch_size: int = 4
    lr: float = 3e-4
    weight_decay: float = 0.01
    betas: tuple[float, float] = (0.9, 0.95)
    grad_clip: float = 1.0
    warmup_steps: int = 100
    ema_decay: float = 0.999

    views_per_sample: int = 4
    min_observed_views: int = 1
    depth_loss_weight: float = 1.0
    text_loss_weight: float = 0.1
    timestep_distribution: str = "logit_normal"
    timestep_shift: float = 1.0

    seed: int = 0
    device: str = "cpu"
    dtype: str = "float32"
    num_workers: int = 0
    log_every: int = 50
    ckpt_every: int = 500
    out_dir: str = "runs/atlas-tiny"
    dataset: str = "synthetic"
    data_root: str | None = None
    scenes: int = 512


def _filter(cls, data: dict[str, Any]) -> dict[str, Any]:
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    return {k: v for k, v in data.items() if k in known}


def load_config(path: str | Path) -> tuple[AtlasConfig, TrainConfig]:
    """Load a JSON config with ``model`` and ``train`` sections."""
    raw = json.loads(Path(path).read_text())
    model = AtlasConfig(**_filter(AtlasConfig, raw.get("model", {})))
    train = TrainConfig(**_filter(TrainConfig, raw.get("train", {})))
    if isinstance(train.betas, list):
        train.betas = tuple(train.betas)
    return model, train
