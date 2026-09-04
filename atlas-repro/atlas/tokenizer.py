"""Latent tokenizers for the continuous modalities.

The transformer never sees raw pixels: images are compressed to a latent grid
first, and it is that grid which is patchified into tokens and denoised by the
rectified flow.  Two tokenizers are provided:

``IdentityTokenizer``
    A pass-through (``downsample = 1``).  Latents are pixels, so the whole
    pipeline trains end-to-end with no pretraining stage -- the right choice
    for the small CPU-scale reproduction and for depth, which is smooth
    enough that compressing it buys nothing.

``ImageVAE``
    A convolutional KL autoencoder with a 4x or 8x spatial reduction, trained
    separately by ``atlas/train_vae.py``.  This is what makes megapixel-scale
    generation tractable, exactly as in the systems Atlas belongs to.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import Tensor, nn

__all__ = [
    "Tokenizer",
    "IdentityTokenizer",
    "ImageVAE",
    "DiagonalGaussian",
    "build_tokenizer",
    "load_pretrained_vae",
]


class Tokenizer(nn.Module):
    """Common interface: ``encode``/``decode`` between pixels and latents."""

    downsample: int = 1
    latent_channels: int = 3

    def encode(self, x: Tensor) -> Tensor:  # pragma: no cover - interface
        raise NotImplementedError

    def decode(self, z: Tensor) -> Tensor:  # pragma: no cover - interface
        raise NotImplementedError

    def latent_size(self, height: int, width: int) -> tuple[int, int]:
        if height % self.downsample or width % self.downsample:
            raise ValueError(
                f"image size {height}x{width} is not divisible by tokenizer downsample {self.downsample}"
            )
        return height // self.downsample, width // self.downsample


class IdentityTokenizer(Tokenizer):
    """Latents are the pixels themselves."""

    def __init__(self, channels: int = 3):
        super().__init__()
        self.downsample = 1
        self.latent_channels = channels

    def encode(self, x: Tensor) -> Tensor:
        return x

    def decode(self, z: Tensor) -> Tensor:
        return z


@dataclass
class DiagonalGaussian:
    """Posterior of the VAE encoder."""

    mean: Tensor
    logvar: Tensor

    def sample(self, generator: torch.Generator | None = None) -> Tensor:
        std = (0.5 * self.logvar).exp()
        eps = torch.randn(self.mean.shape, device=self.mean.device, dtype=self.mean.dtype, generator=generator)
        return self.mean + std * eps

    def kl(self) -> Tensor:
        """Per-sample KL to ``N(0, I)``."""
        return 0.5 * (self.mean.pow(2) + self.logvar.exp() - 1.0 - self.logvar).flatten(1).sum(1)


class _ResBlock(nn.Module):
    def __init__(self, channels: int, groups: int = 8):
        super().__init__()
        groups = min(groups, channels)
        self.norm1 = nn.GroupNorm(groups, channels)
        self.conv1 = nn.Conv2d(channels, channels, 3, padding=1)
        self.norm2 = nn.GroupNorm(groups, channels)
        self.conv2 = nn.Conv2d(channels, channels, 3, padding=1)
        nn.init.zeros_(self.conv2.weight)
        nn.init.zeros_(self.conv2.bias)

    def forward(self, x: Tensor) -> Tensor:
        h = self.conv1(F.silu(self.norm1(x)))
        h = self.conv2(F.silu(self.norm2(h)))
        return x + h


class ImageVAE(Tokenizer):
    """A small KL autoencoder with a power-of-two spatial reduction."""

    def __init__(
        self,
        in_channels: int = 3,
        latent_channels: int = 4,
        base_channels: int = 64,
        downsample: int = 4,
        blocks_per_stage: int = 2,
        scaling_factor: float = 1.0,
    ):
        super().__init__()
        if downsample < 1 or (downsample & (downsample - 1)):
            raise ValueError("downsample must be a power of two")
        self.downsample = downsample
        self.latent_channels = latent_channels
        self.scaling_factor = scaling_factor
        n_stages = int(downsample).bit_length() - 1

        # -- encoder --
        enc: list[nn.Module] = [nn.Conv2d(in_channels, base_channels, 3, padding=1)]
        ch = base_channels
        for stage in range(n_stages):
            for _ in range(blocks_per_stage):
                enc.append(_ResBlock(ch))
            out_ch = min(ch * 2, base_channels * 4)
            enc.append(nn.Conv2d(ch, out_ch, 3, stride=2, padding=1))
            ch = out_ch
        for _ in range(blocks_per_stage):
            enc.append(_ResBlock(ch))
        enc.append(nn.GroupNorm(min(8, ch), ch))
        enc.append(nn.SiLU())
        enc.append(nn.Conv2d(ch, 2 * latent_channels, 3, padding=1))
        self.encoder = nn.Sequential(*enc)

        # -- decoder --
        dec: list[nn.Module] = [nn.Conv2d(latent_channels, ch, 3, padding=1)]
        for _ in range(blocks_per_stage):
            dec.append(_ResBlock(ch))
        for stage in range(n_stages):
            out_ch = max(ch // 2, base_channels)
            dec.append(nn.Upsample(scale_factor=2, mode="nearest"))
            dec.append(nn.Conv2d(ch, out_ch, 3, padding=1))
            ch = out_ch
            for _ in range(blocks_per_stage):
                dec.append(_ResBlock(ch))
        dec.append(nn.GroupNorm(min(8, ch), ch))
        dec.append(nn.SiLU())
        dec.append(nn.Conv2d(ch, in_channels, 3, padding=1))
        self.decoder = nn.Sequential(*dec)

    def posterior(self, x: Tensor) -> DiagonalGaussian:
        mean, logvar = self.encoder(x).chunk(2, dim=1)
        return DiagonalGaussian(mean, logvar.clamp(-30.0, 20.0))

    def encode(self, x: Tensor, sample: bool = False) -> Tensor:
        post = self.posterior(x)
        z = post.sample() if sample else post.mean
        return z * self.scaling_factor

    def decode(self, z: Tensor) -> Tensor:
        return self.decoder(z / self.scaling_factor)

    def forward(self, x: Tensor) -> tuple[Tensor, DiagonalGaussian]:
        post = self.posterior(x)
        return self.decoder(post.sample()), post


def load_pretrained_vae(path, vae: "ImageVAE") -> "ImageVAE":
    """Load weights written by ``atlas.train_vae`` into ``vae``, in place.

    The tokenizer is trained separately and then frozen, so a mismatch between
    the checkpoint and the model config would otherwise surface as a silently
    wrong latent space rather than an error.
    """
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    for key, attr in (("downsample", "downsample"), ("latent_channels", "latent_channels")):
        if key in ckpt and int(ckpt[key]) != int(getattr(vae, attr)):
            raise ValueError(
                f"VAE checkpoint has {key}={ckpt[key]} but the model config says {getattr(vae, attr)}"
            )
    vae.load_state_dict(ckpt["vae"])
    if "scaling_factor" in ckpt:
        vae.scaling_factor = float(ckpt["scaling_factor"])
    return vae


def build_tokenizer(kind: str, **kwargs) -> Tokenizer:
    if kind == "identity":
        return IdentityTokenizer(**kwargs)
    if kind == "vae":
        return ImageVAE(**kwargs)
    raise ValueError(f"unknown tokenizer {kind!r}")
