"""The Atlas backbone: one transformer over the whole spatial context.

A single stack of blocks consumes text tokens, image latent tokens and depth
latent tokens together.  Two details make it a *spatial* model rather than a
sequence model that happens to see pictures:

1.  **Per-element modulation.**  Each element carries its own rectified-flow
    timestep, so adaLN modulation is computed per token from the timestep of
    the element that token belongs to.  Clean context and noisy targets then
    coexist in one forward pass.
2.  **Axial RoPE over (element, row, column).**  Positions are relative along
    each axis independently, so the model generalises to more views and to
    resolutions it was not trained on.  Absolute 3D grounding is *not* done
    here -- it comes from the Plucker ray features added to each visual token
    in :mod:`atlas.model`.
"""

from __future__ import annotations

import math

import torch
import torch.nn.functional as F
from torch import Tensor, nn

__all__ = ["Transformer", "TransformerBlock", "TimestepEmbedding", "RMSNorm", "AxialRoPE"]


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6, elementwise_affine: bool = True):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim)) if elementwise_affine else None

    def forward(self, x: Tensor) -> Tensor:
        dtype = x.dtype
        x = x.float()
        x = x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps)
        x = x.to(dtype)
        return x if self.weight is None else x * self.weight


class TimestepEmbedding(nn.Module):
    """Sinusoidal encoding of ``t in [0, 1]`` followed by an MLP."""

    def __init__(self, dim: int, frequency_dim: int = 256, max_period: float = 10_000.0):
        super().__init__()
        if frequency_dim % 2:
            raise ValueError("frequency_dim must be even")
        self.frequency_dim = frequency_dim
        self.max_period = max_period
        self.mlp = nn.Sequential(nn.Linear(frequency_dim, dim), nn.SiLU(), nn.Linear(dim, dim))

    def forward(self, t: Tensor) -> Tensor:
        half = self.frequency_dim // 2
        freqs = torch.exp(
            -math.log(self.max_period)
            * torch.arange(half, device=t.device, dtype=torch.float32)
            / half
        )
        # Scale to a wide range so that nearby timesteps stay distinguishable.
        args = t.float().reshape(-1, 1) * 1000.0 * freqs[None]
        emb = torch.cat((args.cos(), args.sin()), dim=-1)
        return self.mlp(emb.to(self.mlp[0].weight.dtype)).reshape(*t.shape, -1)


class AxialRoPE(nn.Module):
    """Rotary embeddings applied independently along several position axes."""

    def __init__(self, head_dim: int, n_axes: int = 3, base: float = 10_000.0):
        super().__init__()
        if head_dim % (2 * n_axes):
            raise ValueError(f"head_dim {head_dim} must be divisible by 2 * n_axes ({2 * n_axes})")
        self.head_dim = head_dim
        self.n_axes = n_axes
        self.dim_per_axis = head_dim // n_axes
        half = self.dim_per_axis // 2
        inv_freq = 1.0 / (base ** (torch.arange(half, dtype=torch.float32) / half))
        self.register_buffer("inv_freq", inv_freq, persistent=False)

    def _cos_sin(self, positions: Tensor) -> tuple[Tensor, Tensor]:
        # positions: (S, n_axes) -> angles (S, head_dim / 2)
        angles = positions.float()[..., None] * self.inv_freq[None, None, :]
        angles = angles.reshape(positions.shape[0], -1)
        return angles.cos(), angles.sin()

    def forward(self, x: Tensor, positions: Tensor) -> Tensor:
        """Rotate ``x`` of shape ``(B, H, S, D)`` by ``positions`` ``(S, n_axes)``."""
        if positions.shape[-1] != self.n_axes:
            raise ValueError(f"expected {self.n_axes} position axes, got {positions.shape[-1]}")
        cos, sin = self._cos_sin(positions)
        cos = cos[None, None].to(x.dtype)
        sin = sin[None, None].to(x.dtype)
        x1, x2 = x.reshape(*x.shape[:-1], -1, 2).unbind(-1)
        out = torch.stack((x1 * cos - x2 * sin, x1 * sin + x2 * cos), dim=-1)
        return out.reshape(*x.shape)


class Attention(nn.Module):
    def __init__(self, dim: int, n_heads: int, rope: AxialRoPE | None = None, qk_norm: bool = True):
        super().__init__()
        if dim % n_heads:
            raise ValueError(f"dim {dim} not divisible by n_heads {n_heads}")
        self.n_heads = n_heads
        self.head_dim = dim // n_heads
        self.qkv = nn.Linear(dim, 3 * dim, bias=False)
        self.proj = nn.Linear(dim, dim, bias=False)
        self.rope = rope
        self.q_norm = RMSNorm(self.head_dim) if qk_norm else nn.Identity()
        self.k_norm = RMSNorm(self.head_dim) if qk_norm else nn.Identity()

    def forward(self, x: Tensor, positions: Tensor | None = None, mask: Tensor | None = None) -> Tensor:
        b, s, _ = x.shape
        qkv = self.qkv(x).reshape(b, s, 3, self.n_heads, self.head_dim)
        q, k, v = qkv.permute(2, 0, 3, 1, 4)
        q, k = self.q_norm(q), self.k_norm(k)
        if self.rope is not None and positions is not None:
            q = self.rope(q, positions)
            k = self.rope(k, positions)
        attn_mask = None if mask is None else mask[None, None]
        out = F.scaled_dot_product_attention(q, k, v, attn_mask=attn_mask)
        return self.proj(out.transpose(1, 2).reshape(b, s, -1))


class FeedForward(nn.Module):
    """SwiGLU MLP."""

    def __init__(self, dim: int, hidden_mult: float = 4.0):
        super().__init__()
        hidden = int(2 * hidden_mult * dim / 3)
        hidden = 64 * ((hidden + 63) // 64)
        self.w1 = nn.Linear(dim, hidden, bias=False)
        self.w3 = nn.Linear(dim, hidden, bias=False)
        self.w2 = nn.Linear(hidden, dim, bias=False)

    def forward(self, x: Tensor) -> Tensor:
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class TransformerBlock(nn.Module):
    """Pre-norm block with per-token adaLN-Zero conditioning."""

    def __init__(self, dim: int, n_heads: int, rope: AxialRoPE | None = None, hidden_mult: float = 4.0):
        super().__init__()
        self.norm1 = RMSNorm(dim, elementwise_affine=False)
        self.attn = Attention(dim, n_heads, rope=rope)
        self.norm2 = RMSNorm(dim, elementwise_affine=False)
        self.mlp = FeedForward(dim, hidden_mult)
        self.modulation = nn.Sequential(nn.SiLU(), nn.Linear(dim, 6 * dim))
        # Zero init: every block starts as the identity, which keeps very deep
        # stacks stable at the start of training.
        nn.init.zeros_(self.modulation[1].weight)
        nn.init.zeros_(self.modulation[1].bias)

    def forward(self, x: Tensor, cond: Tensor, positions: Tensor | None = None, mask: Tensor | None = None) -> Tensor:
        shift1, scale1, gate1, shift2, scale2, gate2 = self.modulation(cond).chunk(6, dim=-1)
        h = self.norm1(x) * (1 + scale1) + shift1
        x = x + gate1 * self.attn(h, positions=positions, mask=mask)
        h = self.norm2(x) * (1 + scale2) + shift2
        x = x + gate2 * self.mlp(h)
        return x


class Transformer(nn.Module):
    """A stack of :class:`TransformerBlock` with a modulated output norm."""

    def __init__(self, dim: int, depth: int, n_heads: int, hidden_mult: float = 4.0, rope_axes: int = 3):
        super().__init__()
        head_dim = dim // n_heads
        self.rope = AxialRoPE(head_dim, n_axes=rope_axes)
        self.blocks = nn.ModuleList(
            [TransformerBlock(dim, n_heads, rope=self.rope, hidden_mult=hidden_mult) for _ in range(depth)]
        )
        self.norm_out = RMSNorm(dim, elementwise_affine=False)
        self.modulation_out = nn.Sequential(nn.SiLU(), nn.Linear(dim, 2 * dim))
        nn.init.zeros_(self.modulation_out[1].weight)
        nn.init.zeros_(self.modulation_out[1].bias)

    def forward(self, x: Tensor, cond: Tensor, positions: Tensor | None = None, mask: Tensor | None = None) -> Tensor:
        for block in self.blocks:
            x = block(x, cond, positions=positions, mask=mask)
        shift, scale = self.modulation_out(cond).chunk(2, dim=-1)
        return self.norm_out(x) * (1 + scale) + shift
