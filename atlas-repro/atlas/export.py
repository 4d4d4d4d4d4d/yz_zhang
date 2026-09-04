"""Exporting a spatial context as 3D.

Because Atlas predicts depth in the same context as RGB, every generated view
already carries geometry.  Unprojecting each view and concatenating gives a
fused point cloud with no separate alignment step -- and the same points,
given a covariance and an opacity, are a 3D Gaussian splat.  Both are written
as PLY: point clouds in the standard vertex layout, splats in the layout the
common web viewers expect.
"""

from __future__ import annotations

import struct
from pathlib import Path

import torch
from torch import Tensor

__all__ = ["write_point_cloud_ply", "write_gaussian_splat_ply", "points_from_context"]


def _to_uint8(rgb: Tensor) -> Tensor:
    """``[-1, 1]`` float RGB -> ``[0, 255]`` uint8."""
    return ((rgb.clamp(-1.0, 1.0) + 1.0) * 127.5).round().to(torch.uint8)


def write_point_cloud_ply(path: str | Path, points: Tensor, colors: Tensor | None = None) -> Path:
    """Write ``(N, 3)`` points (and optional ``(N, 3)`` RGB in ``[-1, 1]``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    points = points.detach().float().reshape(-1, 3).cpu()
    n = points.shape[0]
    if colors is not None:
        colors = _to_uint8(colors.detach().reshape(-1, 3).cpu())
        if colors.shape[0] != n:
            raise ValueError(f"{n} points but {colors.shape[0]} colours")

    header = ["ply", "format binary_little_endian 1.0", f"element vertex {n}"]
    header += ["property float x", "property float y", "property float z"]
    if colors is not None:
        header += ["property uchar red", "property uchar green", "property uchar blue"]
    header += ["end_header", ""]

    with path.open("wb") as f:
        f.write("\n".join(header).encode("ascii"))
        if colors is None:
            f.write(points.numpy().astype("<f4").tobytes())
        else:
            for i in range(n):
                f.write(struct.pack("<fff", *points[i].tolist()))
                f.write(struct.pack("<BBB", *colors[i].tolist()))
    return path


def write_gaussian_splat_ply(
    path: str | Path,
    points: Tensor,
    colors: Tensor,
    *,
    scale: float | Tensor = 0.01,
    opacity: float = 0.9,
) -> Path:
    """Write points as isotropic 3D Gaussians in the standard splat PLY layout.

    Colours are stored as zeroth-order spherical harmonics, scales as logs and
    opacity as a logit, matching the convention every splat viewer assumes.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    points = points.detach().float().reshape(-1, 3).cpu()
    colors = colors.detach().float().reshape(-1, 3).cpu()
    n = points.shape[0]
    if colors.shape[0] != n:
        raise ValueError(f"{n} points but {colors.shape[0]} colours")

    # SH band 0: c = 0.5 + C0 * dc  =>  dc = (c - 0.5) / C0
    c0 = 0.28209479177387814
    rgb01 = (colors.clamp(-1.0, 1.0) + 1.0) * 0.5
    dc = (rgb01 - 0.5) / c0

    if not torch.is_tensor(scale):
        scale = torch.full((n, 1), float(scale))
    scale = scale.reshape(-1, 1).expand(n, 3).clamp_min(1e-8)
    log_scale = scale.log()
    logit_opacity = torch.logit(torch.tensor(opacity).clamp(1e-4, 1 - 1e-4))

    header = [
        "ply",
        "format binary_little_endian 1.0",
        f"element vertex {n}",
        "property float x", "property float y", "property float z",
        "property float nx", "property float ny", "property float nz",
        "property float f_dc_0", "property float f_dc_1", "property float f_dc_2",
        "property float opacity",
        "property float scale_0", "property float scale_1", "property float scale_2",
        "property float rot_0", "property float rot_1", "property float rot_2", "property float rot_3",
        "end_header", "",
    ]

    with path.open("wb") as f:
        f.write("\n".join(header).encode("ascii"))
        for i in range(n):
            f.write(struct.pack("<fff", *points[i].tolist()))
            f.write(struct.pack("<fff", 0.0, 0.0, 0.0))            # unused normals
            f.write(struct.pack("<fff", *dc[i].tolist()))
            f.write(struct.pack("<f", float(logit_opacity)))
            f.write(struct.pack("<fff", *log_scale[i].tolist()))
            f.write(struct.pack("<ffff", 1.0, 0.0, 0.0, 0.0))      # identity rotation
    return path


def points_from_context(
    points: Tensor,
    images: Tensor,
    *,
    max_depth: float | None = None,
    depth: Tensor | None = None,
    stride: int = 1,
) -> tuple[Tensor, Tensor]:
    """Flatten per-view pointmaps and images into one coloured cloud.

    ``points`` is ``(V, H, W, 3)`` and ``images`` ``(V, 3, H, W)``.  Points
    beyond ``max_depth`` are dropped -- rays that hit nothing produce points at
    the far plane, and keeping them would bury the scene in a shell.
    """
    if points.ndim != 4 or points.shape[-1] != 3:
        raise ValueError(f"points must be (V,H,W,3), got {tuple(points.shape)}")
    if images.shape[0] != points.shape[0]:
        raise ValueError(
            f"{points.shape[0]} pointmaps but {images.shape[0]} images -- every view "
            "passed here must have both colour and geometry"
        )
    if depth is not None and depth.shape[0] != points.shape[0]:
        raise ValueError(f"{points.shape[0]} pointmaps but {depth.shape[0]} depth maps")

    pts = points[:, ::stride, ::stride].reshape(-1, 3)
    rgb = images[:, :, ::stride, ::stride].permute(0, 2, 3, 1).reshape(-1, 3)

    if max_depth is not None and depth is not None:
        keep = depth[:, ::stride, ::stride].reshape(-1) < max_depth
        pts, rgb = pts[keep], rgb[keep]
    return pts, rgb
