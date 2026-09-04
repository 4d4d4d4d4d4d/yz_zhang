"""Depth parameterisation.

Raw metric depth is unbounded and heavily skewed towards small values, which
makes it a poor target for a diffusion model whose noise is isotropic.  Atlas
predicts depth alongside RGB in the same latent space, so depth needs a
bounded, roughly perceptually-uniform encoding.  We use normalised log depth,
which spends resolution where relative error matters and maps cleanly to
``[-1, 1]``.
"""

from __future__ import annotations

import math

import torch
from torch import Tensor

__all__ = ["encode_depth", "decode_depth", "DEPTH_FAR"]

#: Far plane in normalised scene units (scenes are canonicalised so that the
#: mean camera-to-centroid distance is 1).
DEPTH_FAR = 20.0


def encode_depth(depth: Tensor, far: float = DEPTH_FAR) -> Tensor:
    """Metric depth -> ``[-1, 1]`` log-depth code.  Non-positive depth is invalid."""
    scale = math.log1p(far)
    z = torch.log1p(depth.clamp(min=0.0, max=far)) / scale
    return 2.0 * z - 1.0


def decode_depth(code: Tensor, far: float = DEPTH_FAR) -> Tensor:
    """Inverse of :func:`encode_depth`, clamped back into the valid range."""
    scale = math.log1p(far)
    z = ((code.clamp(-1.0, 1.0) + 1.0) * 0.5) * scale
    return torch.expm1(z)
