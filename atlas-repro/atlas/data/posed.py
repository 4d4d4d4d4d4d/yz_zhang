"""Loader for real posed-image datasets.

The reproduction trains on procedural scenes so that it runs anywhere, but the
architecture takes posed frames of any origin.  This loader reads the common
"posed frames" layout produced by COLMAP exports and by the standard
re-packagings of RealEstate10K / CO3D / ScanNet:

    root/
      scene_0001/
        meta.json         {"K": [[...]], "frames": [{"file": "...", "w2c": [[...]], "depth": "..."}]}
        images/0000.png
        depth/0000.npy    (optional, metres)

Depth is optional -- without it the depth elements simply carry no
supervision, and the model still trains for generation.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import Tensor
from torch.utils.data import Dataset

from ..cameras import Cameras, invert_rigid
from ..depth_repr import DEPTH_FAR

__all__ = ["PosedFrames"]


def _load_image(path: Path, size: int) -> Tensor:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("Pillow is required to read image files; pip install pillow") from exc

    img = Image.open(path).convert("RGB").resize((size, size), Image.BILINEAR)
    arr = torch.frombuffer(bytearray(img.tobytes()), dtype=torch.uint8).clone()
    arr = arr.reshape(size, size, 3).permute(2, 0, 1).float() / 255.0
    return arr * 2.0 - 1.0


class PosedFrames(Dataset):
    """Sample ``views`` consecutive frames from each posed scene."""

    def __init__(
        self,
        root: str | Path,
        *,
        image_size: int = 64,
        views: int = 4,
        stride: int = 1,
        normalize_scale: bool = True,
    ):
        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"dataset root {self.root} does not exist")
        self.image_size = int(image_size)
        self.views = int(views)
        self.stride = int(stride)
        self.normalize_scale = normalize_scale

        self.scenes = sorted(p for p in self.root.iterdir() if (p / "meta.json").is_file())
        if not self.scenes:
            raise FileNotFoundError(f"no scenes with meta.json found under {self.root}")

    def __len__(self) -> int:
        return len(self.scenes)

    def __getitem__(self, index: int) -> dict:
        scene = self.scenes[index]
        meta = json.loads((scene / "meta.json").read_text())
        frames = meta["frames"]

        span = self.views * self.stride
        if len(frames) < span:
            raise ValueError(f"scene {scene.name} has {len(frames)} frames, need {span}")
        start = int(torch.randint(0, len(frames) - span + 1, (1,)))
        chosen = frames[start : start + span : self.stride]

        images, depths, valids, w2cs = [], [], [], []
        for frame in chosen:
            img = _load_image(scene / frame["file"], self.image_size)
            images.append(img)
            w2cs.append(torch.tensor(frame["w2c"], dtype=torch.float32))

            if frame.get("depth"):
                import numpy as np

                raw = torch.from_numpy(np.load(scene / frame["depth"])).float()
                raw = torch.nn.functional.interpolate(
                    raw[None, None], size=(self.image_size, self.image_size), mode="nearest"
                )[0, 0]
                depths.append(raw)
            else:
                depths.append(torch.zeros(self.image_size, self.image_size))

        k = torch.tensor(meta["K"], dtype=torch.float32)
        # Intrinsics are stored for the source resolution; rescale to ours.
        src_h = float(meta.get("height", self.image_size))
        src_w = float(meta.get("width", self.image_size))
        k = k.clone()
        k[0] *= self.image_size / src_w
        k[1] *= self.image_size / src_h
        k = k[None].expand(len(chosen), 3, 3).contiguous()

        w2c = torch.stack(w2cs)
        depth = torch.stack(depths)
        has_depth = any(f.get("depth") for f in chosen)
        cams = Cameras(w2c, k, self.image_size, self.image_size)

        if self.normalize_scale:
            centers = cams.centers
            scale = (centers - centers.mean(0, keepdim=True)).norm(dim=-1).mean().clamp_min(1e-6)
            c2w = cams.c2w.clone()
            c2w[:, :3, 3] /= scale
            w2c = invert_rigid(c2w)
            depth = depth / scale

        # Same exclusion as the synthetic loader: depth past the representable
        # far plane is supervised but never scored.  Frames with no depth file
        # at all are entirely invalid.
        valid = (depth > 0) & (depth <= DEPTH_FAR) if has_depth else torch.zeros_like(depth, dtype=torch.bool)

        return {
            "image": torch.stack(images),
            "depth": depth,
            "depth_valid": valid,
            "w2c": w2c,
            "K": k,
            "caption": meta.get("caption", "a scene"),
        }
