"""Camera geometry for Atlas' spatial context.

Every visual element in Atlas is *anchored in 3D*: it enters the sequence
together with an explicit camera pose.  The pose is turned into a dense,
per-patch Plucker ray embedding so that each visual token literally carries
the 3D ray it observes.  This module holds that machinery.

Conventions (OpenCV):
  * ``w2c`` is a world-to-camera rigid transform, shape ``(..., 4, 4)``.
  * The camera looks down ``+z``; ``x`` is right and ``y`` is down.
  * ``K`` is a pinhole intrinsics matrix, shape ``(..., 3, 3)``, in pixels.
"""

from __future__ import annotations

import torch
from torch import Tensor

__all__ = [
    "Cameras",
    "invert_rigid",
    "plucker_rays",
    "pixel_grid",
    "unproject_depth",
    "look_at",
    "normalize_scene_scale",
]


def invert_rigid(t: Tensor) -> Tensor:
    """Invert a batch of rigid ``(..., 4, 4)`` transforms without a solve."""
    r = t[..., :3, :3]
    trans = t[..., :3, 3:]
    r_inv = r.transpose(-1, -2)
    out = torch.zeros_like(t)
    out[..., :3, :3] = r_inv
    out[..., :3, 3:] = -r_inv @ trans
    out[..., 3, 3] = 1.0
    return out


def pixel_grid(height: int, width: int, *, device=None, dtype=torch.float32) -> Tensor:
    """Pixel centres as ``(H, W, 2)`` in ``(x, y)`` order."""
    ys, xs = torch.meshgrid(
        torch.arange(height, device=device, dtype=dtype) + 0.5,
        torch.arange(width, device=device, dtype=dtype) + 0.5,
        indexing="ij",
    )
    return torch.stack((xs, ys), dim=-1)


class Cameras:
    """A batch of pinhole cameras.

    Parameters
    ----------
    w2c:
        World-to-camera transforms, ``(..., 4, 4)``.
    K:
        Intrinsics in pixels, ``(..., 3, 3)``.
    height, width:
        Image size the intrinsics refer to.
    """

    def __init__(self, w2c: Tensor, K: Tensor, height: int, width: int):
        if w2c.shape[-2:] != (4, 4):
            raise ValueError(f"w2c must be (...,4,4), got {tuple(w2c.shape)}")
        if K.shape[-2:] != (3, 3):
            raise ValueError(f"K must be (...,3,3), got {tuple(K.shape)}")
        if w2c.shape[:-2] != K.shape[:-2]:
            raise ValueError("w2c and K must share batch dims")
        self.w2c = w2c
        self.K = K
        self.height = int(height)
        self.width = int(width)

    # -- basic accessors -------------------------------------------------
    @property
    def batch_shape(self) -> torch.Size:
        return self.w2c.shape[:-2]

    @property
    def device(self):
        return self.w2c.device

    @property
    def dtype(self):
        return self.w2c.dtype

    @property
    def c2w(self) -> Tensor:
        return invert_rigid(self.w2c)

    @property
    def centers(self) -> Tensor:
        """Camera centres in world space, ``(..., 3)``."""
        return self.c2w[..., :3, 3]

    def to(self, *args, **kwargs) -> "Cameras":
        return Cameras(self.w2c.to(*args, **kwargs), self.K.to(*args, **kwargs), self.height, self.width)

    def reshape(self, *shape: int) -> "Cameras":
        return Cameras(self.w2c.reshape(*shape, 4, 4), self.K.reshape(*shape, 3, 3), self.height, self.width)

    def __getitem__(self, idx) -> "Cameras":
        return Cameras(self.w2c[idx], self.K[idx], self.height, self.width)

    def __len__(self) -> int:
        return int(self.batch_shape[0]) if self.batch_shape else 1

    # -- ray geometry ----------------------------------------------------
    def rays(self, height: int | None = None, width: int | None = None) -> tuple[Tensor, Tensor]:
        """World-space ray origins and unit directions.

        Returns two tensors of shape ``(..., h, w, 3)``.  ``h``/``w`` default
        to the camera's own resolution; passing a smaller grid samples the
        rays at patch centres, which is how visual tokens get their pose.
        """
        h = self.height if height is None else height
        w = self.width if width is None else width

        uv = pixel_grid(h, w, device=self.device, dtype=self.dtype)
        # Rescale patch-centre coordinates back into full-resolution pixels.
        uv = uv * uv.new_tensor([self.width / w, self.height / h])

        ones = torch.ones_like(uv[..., :1])
        uv1 = torch.cat((uv, ones), dim=-1)  # (h, w, 3)

        k_inv = torch.linalg.inv(self.K.to(torch.float32)).to(self.dtype)
        # (..., 1, 1, 3, 3) @ (h, w, 3, 1) -> (..., h, w, 3)
        dirs_cam = (k_inv[..., None, None, :, :] @ uv1[..., None]).squeeze(-1)

        c2w = self.c2w
        rot = c2w[..., None, None, :3, :3]
        dirs_world = (rot @ dirs_cam[..., None]).squeeze(-1)
        dirs_world = torch.nn.functional.normalize(dirs_world, dim=-1)

        origins = c2w[..., :3, 3][..., None, None, :].expand_as(dirs_world)
        return origins, dirs_world

    def plucker(self, height: int | None = None, width: int | None = None) -> Tensor:
        """Per-ray Plucker embedding, ``(..., h, w, 6)``."""
        origins, dirs = self.rays(height, width)
        return plucker_rays(origins, dirs)

    def project(self, points_world: Tensor) -> tuple[Tensor, Tensor]:
        """Project world points to pixels.

        ``points_world`` is ``(..., N, 3)``; returns pixel coords ``(..., N, 2)``
        and camera-space depth ``(..., N)``.
        """
        r = self.w2c[..., None, :3, :3]
        t = self.w2c[..., None, :3, 3]
        cam = (r @ points_world[..., None]).squeeze(-1) + t
        depth = cam[..., 2]
        uvw = (self.K[..., None, :, :] @ cam[..., None]).squeeze(-1)
        uv = uvw[..., :2] / uvw[..., 2:].clamp_min(1e-8)
        return uv, depth


def plucker_rays(origins: Tensor, directions: Tensor) -> Tensor:
    """Plucker coordinates ``(d, o x d)`` for unit directions ``d``.

    The moment ``o x d`` is invariant to sliding the origin along the ray, so
    this is a genuine encoding of the *line* in space rather than of the
    particular camera centre -- which is what makes it a good positional code
    for a model that must reason about where a pixel looks, not where it sits.
    """
    directions = torch.nn.functional.normalize(directions, dim=-1)
    moment = torch.cross(origins, directions, dim=-1)
    return torch.cat((directions, moment), dim=-1)


def unproject_depth(cameras: Cameras, depth: Tensor) -> Tensor:
    """Lift a depth map to a world-space pointmap.

    ``depth`` is ``(..., H, W)`` of *z* distances (not ray lengths); the result
    is ``(..., H, W, 3)``.  This is the operation that turns Atlas' predicted
    depth elements into the pointmaps its 3D reconstruction is scored on.
    """
    h, w = depth.shape[-2:]
    origins, dirs = cameras.rays(h, w)

    # dirs are unit vectors; convert z-depth to along-ray distance.
    fwd = cameras.c2w[..., None, None, :3, 2]
    cos = (dirs * fwd).sum(-1, keepdim=True).clamp_min(1e-6)
    return origins + dirs * (depth[..., None] / cos)


def look_at(eye: Tensor, target: Tensor, up: Tensor | None = None) -> Tensor:
    """Build a world-to-camera transform looking from ``eye`` at ``target``."""
    if up is None:
        up = eye.new_tensor([0.0, -1.0, 0.0]).expand_as(eye)
    fwd = torch.nn.functional.normalize(target - eye, dim=-1)
    # Guard against a degenerate up vector parallel to the view direction.
    if torch.any((fwd * torch.nn.functional.normalize(up, dim=-1)).abs().sum(-1) > 0.999):
        up = up + up.new_tensor([1e-3, 0.0, 1e-3])
    right = torch.nn.functional.normalize(torch.cross(fwd, up, dim=-1), dim=-1)
    true_up = torch.cross(right, fwd, dim=-1)

    r = torch.stack((right, true_up, fwd), dim=-2)  # world -> camera rotation
    w2c = torch.zeros(*eye.shape[:-1], 4, 4, device=eye.device, dtype=eye.dtype)
    w2c[..., :3, :3] = r
    w2c[..., :3, 3] = -(r @ eye[..., None]).squeeze(-1)
    w2c[..., 3, 3] = 1.0
    return w2c


def normalize_scene_scale(cameras: Cameras, depth: Tensor | None = None) -> tuple[Cameras, Tensor]:
    """Rescale a scene so camera centres have unit average distance to origin.

    Atlas' spatial context is scale-free -- absolute metres are unknowable from
    images alone -- so both training and evaluation operate on a canonicalised
    scene.  Returns the rescaled cameras and the scale that was applied.
    """
    centers = cameras.centers.reshape(-1, 3)
    centroid = centers.mean(0, keepdim=True)
    scale = (centers - centroid).norm(dim=-1).mean().clamp_min(1e-6)

    w2c = cameras.w2c.clone()
    c2w = invert_rigid(w2c)
    c2w[..., :3, 3] = (c2w[..., :3, 3] - centroid) / scale
    out = Cameras(invert_rigid(c2w), cameras.K, cameras.height, cameras.width)
    if depth is not None:
        depth = depth / scale
    return out, scale
