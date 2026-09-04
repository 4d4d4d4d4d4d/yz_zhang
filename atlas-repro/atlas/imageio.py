"""Minimal PNG writing, with no image-library dependency.

The reproduction should be able to dump results on a bare Python install, so
this writes PNGs directly with ``zlib`` from the standard library rather than
pulling in Pillow just to save a preview.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import torch
from torch import Tensor

__all__ = ["save_png", "save_grid", "to_uint8", "colorize_depth"]


def to_uint8(image: Tensor) -> Tensor:
    """``(3, H, W)`` or ``(H, W, 3)`` in ``[-1, 1]`` -> ``(H, W, 3)`` uint8."""
    if image.ndim != 3:
        raise ValueError(f"expected a 3-D image, got {tuple(image.shape)}")
    if image.shape[0] in (1, 3) and image.shape[-1] not in (1, 3):
        image = image.permute(1, 2, 0)
    if image.shape[-1] == 1:
        image = image.expand(-1, -1, 3)
    return ((image.detach().float().clamp(-1.0, 1.0) + 1.0) * 127.5).round().to(torch.uint8).cpu()


def save_png(path: str | Path, image: Tensor) -> Path:
    """Write an RGB image in ``[-1, 1]`` to a PNG file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    arr = to_uint8(image)
    height, width, _ = arr.shape
    raw = bytearray()
    data = arr.reshape(height, width * 3).numpy().tobytes()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # per-scanline filter type: none
        raw += data[y * stride : (y + 1) * stride]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    return path


def save_grid(path: str | Path, images: Tensor, *, columns: int | None = None, pad: int = 2) -> Path:
    """Tile ``(N, 3, H, W)`` images into a single PNG."""
    if images.ndim != 4:
        raise ValueError(f"expected (N,3,H,W), got {tuple(images.shape)}")
    n, _, h, w = images.shape
    columns = columns or n
    rows = (n + columns - 1) // columns

    canvas = torch.full((3, rows * (h + pad) + pad, columns * (w + pad) + pad), -1.0)
    for i in range(n):
        r, c = divmod(i, columns)
        y = pad + r * (h + pad)
        x = pad + c * (w + pad)
        canvas[:, y : y + h, x : x + w] = images[i].detach().float().cpu()
    return save_png(path, canvas)


def colorize_depth(depth: Tensor, valid: Tensor | None = None) -> Tensor:
    """Map a depth map to an inverse-depth grey image in ``[-1, 1]``.

    Inverse depth (disparity) is used because it spreads contrast over the
    near field, where depth error actually shows.
    """
    d = depth.detach().float()
    m = (d > 1e-6) if valid is None else valid
    if not bool(m.any()):
        return torch.full((1, *d.shape[-2:]), -1.0)

    disp = torch.where(m, 1.0 / d.clamp_min(1e-6), torch.zeros_like(d))
    lo = disp[m].min()
    hi = disp[m].max()
    norm = (disp - lo) / (hi - lo).clamp_min(1e-8)
    norm = torch.where(m, norm, torch.zeros_like(norm))
    return (norm * 2.0 - 1.0).reshape(1, *d.shape[-2:])
