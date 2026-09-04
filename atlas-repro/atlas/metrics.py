"""Metrics for the three things Atlas is asked to do.

Generation quality is measured with PSNR/LPIPS-free pixel statistics (a full
perceptual metric needs a pretrained backbone we deliberately do not ship),
and 3D reconstruction with the pointmap errors used by the DTU / ETH3D /
ScanNet protocol: mean absolute *relative* error after a scale alignment.
The scale alignment matters -- monocular geometry is only recoverable up to
a global scale, so comparing raw metres would measure the wrong thing.
"""

from __future__ import annotations

import torch
from torch import Tensor

__all__ = ["psnr", "abs_rel", "delta_accuracy", "align_scale", "chamfer_distance", "pointmap_metrics"]


def psnr(pred: Tensor, target: Tensor, data_range: float = 2.0) -> Tensor:
    """PSNR in dB for images in ``[-1, 1]`` (``data_range = 2``)."""
    mse = (pred.float() - target.float()).pow(2).flatten(1).mean(1).clamp_min(1e-12)
    return 10.0 * torch.log10(data_range ** 2 / mse)


def align_scale(pred: Tensor, target: Tensor, valid: Tensor | None = None) -> Tensor:
    """Least-squares scale that best matches ``pred`` to ``target``.

    Returns a ``(B,)`` scale.  Using the median ratio rather than a plain
    least-squares fit keeps a handful of badly wrong pixels from dominating.
    """
    p = pred.flatten(1).float()
    t = target.flatten(1).float()
    if valid is not None:
        m = valid.flatten(1)
    else:
        m = torch.ones_like(p, dtype=torch.bool)
    m = m & (p > 1e-6) & (t > 1e-6)

    scales = []
    for i in range(p.shape[0]):
        sel = m[i]
        scales.append((t[i][sel] / p[i][sel]).median() if sel.any() else torch.ones((), device=p.device))
    return torch.stack(scales)


def abs_rel(pred: Tensor, target: Tensor, valid: Tensor | None = None, align: bool = True) -> Tensor:
    """Mean absolute relative error ``|pred - target| / target``, per sample."""
    p = pred.float()
    t = target.float()
    if align:
        s = align_scale(p, t, valid)
        p = p * s.reshape(-1, *([1] * (p.ndim - 1)))

    m = (t > 1e-6) if valid is None else (valid & (t > 1e-6))
    err = (p - t).abs() / t.clamp_min(1e-6)
    err = torch.where(m, err, torch.zeros_like(err))
    count = m.flatten(1).sum(1).clamp_min(1)
    return err.flatten(1).sum(1) / count


def delta_accuracy(pred: Tensor, target: Tensor, valid: Tensor | None = None, threshold: float = 1.25) -> Tensor:
    """Fraction of pixels with ``max(p/t, t/p) < threshold``, per sample."""
    p = pred.float()
    t = target.float()
    s = align_scale(p, t, valid)
    p = p * s.reshape(-1, *([1] * (p.ndim - 1)))

    m = (t > 1e-6) if valid is None else (valid & (t > 1e-6))
    ratio = torch.maximum(p / t.clamp_min(1e-6), t / p.clamp_min(1e-6))
    good = (ratio < threshold) & m
    return good.flatten(1).sum(1).float() / m.flatten(1).sum(1).clamp_min(1)


def chamfer_distance(a: Tensor, b: Tensor, max_points: int = 4096) -> Tensor:
    """Symmetric Chamfer distance between two ``(B, N, 3)`` point sets."""
    if a.shape[1] > max_points:
        idx = torch.randperm(a.shape[1], device=a.device)[:max_points]
        a = a[:, idx]
    if b.shape[1] > max_points:
        idx = torch.randperm(b.shape[1], device=b.device)[:max_points]
        b = b[:, idx]

    # The default matmul-based expansion of ||a - b||^2 loses several digits
    # to cancellation; an exact Chamfer of a cloud with itself must be 0.
    d = torch.cdist(a.float(), b.float(), compute_mode="donot_use_mm_for_euclid_dist")
    return d.min(dim=2).values.mean(1) + d.min(dim=1).values.mean(1)


def pointmap_metrics(
    pred_depth: Tensor, target_depth: Tensor, valid: Tensor | None = None
) -> dict[str, float]:
    """The standard reconstruction summary reported by ``atlas.eval``."""
    return {
        "abs_rel": float(abs_rel(pred_depth, target_depth, valid).mean()),
        "delta_1.25": float(delta_accuracy(pred_depth, target_depth, valid, 1.25).mean()),
        "delta_1.25^2": float(delta_accuracy(pred_depth, target_depth, valid, 1.25 ** 2).mean()),
    }
