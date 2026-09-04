"""Procedural multi-view worlds with exact geometry.

Reproducing a spatial model needs data whose *pose and depth are known*, not
approximated by structure-from-motion.  This module renders small random
scenes with a vectorised CPU ray tracer, which gives per-pixel ground-truth
depth, exact camera poses and a caption describing the scene -- everything
the spatial context consumes -- with no download and no preprocessing.

Scenes are made of coloured spheres and axis-aligned boxes on a chequered
floor, lit by one directional light plus ambient.  That is deliberately
simple: it is enough to make novel-view synthesis and depth estimation
non-trivial (occlusion, parallax, shading) while staying cheap enough to
train on CPU.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor
from torch.utils.data import Dataset

from ..cameras import Cameras, look_at
from ..depth_repr import DEPTH_FAR

__all__ = ["SyntheticWorlds", "Scene", "render", "random_scene", "orbit_cameras"]

_COLOR_NAMES = {
    "red": (0.85, 0.18, 0.18),
    "green": (0.16, 0.72, 0.30),
    "blue": (0.20, 0.35, 0.90),
    "yellow": (0.92, 0.82, 0.18),
    "purple": (0.60, 0.24, 0.82),
    "orange": (0.95, 0.52, 0.12),
    "cyan": (0.18, 0.78, 0.82),
    "pink": (0.94, 0.48, 0.66),
}
_COUNT_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight")


@dataclass
class Scene:
    """A ray-traceable scene: spheres, axis-aligned boxes and a floor."""

    sphere_centers: Tensor       # (S, 3)
    sphere_radii: Tensor         # (S,)
    sphere_colors: Tensor        # (S, 3)
    box_lo: Tensor               # (B, 3)
    box_hi: Tensor               # (B, 3)
    box_colors: Tensor           # (B, 3)
    floor_y: float
    light_dir: Tensor            # (3,)
    caption: str

    def to(self, device) -> "Scene":
        return Scene(
            self.sphere_centers.to(device), self.sphere_radii.to(device), self.sphere_colors.to(device),
            self.box_lo.to(device), self.box_hi.to(device), self.box_colors.to(device),
            self.floor_y, self.light_dir.to(device), self.caption,
        )


def random_scene(generator: torch.Generator, *, max_spheres: int = 3, max_boxes: int = 2) -> Scene:
    """Sample a random scene and a caption that describes it."""

    def rand(*shape, lo=0.0, hi=1.0):
        return torch.rand(*shape, generator=generator) * (hi - lo) + lo

    names = list(_COLOR_NAMES)
    n_sph = int(torch.randint(1, max_spheres + 1, (1,), generator=generator))
    n_box = int(torch.randint(1, max_boxes + 1, (1,), generator=generator))

    sph_idx = torch.randint(0, len(names), (n_sph,), generator=generator)
    box_idx = torch.randint(0, len(names), (n_box,), generator=generator)

    radii = rand(n_sph, lo=0.25, hi=0.55)
    centers = torch.stack(
        (rand(n_sph, lo=-1.3, hi=1.3), radii - 1.0, rand(n_sph, lo=-1.3, hi=1.3)), dim=-1
    )
    sphere_colors = torch.tensor([_COLOR_NAMES[names[i]] for i in sph_idx.tolist()])

    size = torch.stack(
        (rand(n_box, lo=0.3, hi=0.8), rand(n_box, lo=0.3, hi=1.0), rand(n_box, lo=0.3, hi=0.8)), dim=-1
    )
    base = torch.stack((rand(n_box, lo=-1.3, hi=1.3), torch.full((n_box,), -1.0), rand(n_box, lo=-1.3, hi=1.3)), dim=-1)
    box_lo = base
    box_hi = base + size
    box_colors = torch.tensor([_COLOR_NAMES[names[i]] for i in box_idx.tolist()])

    light = torch.nn.functional.normalize(
        torch.stack((rand(1, lo=-0.6, hi=0.6)[0], rand(1, lo=0.6, hi=1.0)[0], rand(1, lo=-0.6, hi=0.6)[0])), dim=0
    )

    sph_word = "sphere" if n_sph == 1 else "spheres"
    box_word = "cube" if n_box == 1 else "cubes"
    sph_color = names[int(sph_idx[0])]
    box_color = names[int(box_idx[0])]
    caption = (
        f"a scene with {_COUNT_WORDS[n_sph]} {sph_color} {sph_word} "
        f"and {_COUNT_WORDS[n_box]} {box_color} {box_word} on the floor"
    )

    return Scene(centers, radii, sphere_colors, box_lo, box_hi, box_colors, -1.0, light, caption)


def _intersect_spheres(o: Tensor, d: Tensor, scene: Scene) -> tuple[Tensor, Tensor, Tensor]:
    """Nearest sphere hit.  Returns ``(t, normal, colour)`` with ``t = inf`` on miss."""
    if scene.sphere_centers.numel() == 0:
        inf = torch.full(o.shape[:-1], float("inf"), device=o.device)
        return inf, torch.zeros_like(o), torch.zeros_like(o)

    oc = o[:, None, :] - scene.sphere_centers[None]           # (N, S, 3)
    b = 2.0 * (d[:, None, :] * oc).sum(-1)
    c = (oc * oc).sum(-1) - scene.sphere_radii[None] ** 2
    disc = b * b - 4.0 * c

    sqrt_disc = torch.sqrt(disc.clamp_min(0.0))
    t0 = (-b - sqrt_disc) * 0.5
    t1 = (-b + sqrt_disc) * 0.5
    t = torch.where(t0 > 1e-4, t0, t1)
    t = torch.where((disc > 0) & (t > 1e-4), t, torch.full_like(t, float("inf")))

    best_t, best_i = t.min(dim=1)
    hit_p = o + d * best_t.clamp(max=1e6)[:, None]
    normal = torch.nn.functional.normalize(hit_p - scene.sphere_centers[best_i], dim=-1)
    return best_t, normal, scene.sphere_colors[best_i]


def _intersect_boxes(o: Tensor, d: Tensor, scene: Scene) -> tuple[Tensor, Tensor, Tensor]:
    """Nearest axis-aligned box hit via the slab test."""
    if scene.box_lo.numel() == 0:
        inf = torch.full(o.shape[:-1], float("inf"), device=o.device)
        return inf, torch.zeros_like(o), torch.zeros_like(o)

    inv_d = 1.0 / torch.where(d.abs() < 1e-8, torch.full_like(d, 1e-8), d)
    ta = (scene.box_lo[None] - o[:, None, :]) * inv_d[:, None, :]
    tb = (scene.box_hi[None] - o[:, None, :]) * inv_d[:, None, :]
    t_near = torch.minimum(ta, tb).max(dim=-1).values
    t_far = torch.maximum(ta, tb).min(dim=-1).values

    t = torch.where((t_far >= t_near.clamp_min(0.0)) & (t_near > 1e-4), t_near, torch.full_like(t_near, float("inf")))
    best_t, best_i = t.min(dim=1)

    hit_p = o + d * best_t.clamp(max=1e6)[:, None]
    lo, hi = scene.box_lo[best_i], scene.box_hi[best_i]
    center = 0.5 * (lo + hi)
    half = 0.5 * (hi - lo).clamp_min(1e-6)
    rel = (hit_p - center) / half
    # The dominant axis of the local coordinate identifies the face that was hit.
    axis = rel.abs().argmax(dim=-1, keepdim=True)
    normal = torch.zeros_like(rel).scatter_(1, axis, torch.sign(rel.gather(1, axis)))
    return best_t, normal, scene.box_colors[best_i]


def _intersect_floor(o: Tensor, d: Tensor, scene: Scene) -> tuple[Tensor, Tensor, Tensor]:
    t = (scene.floor_y - o[:, 1]) / torch.where(d[:, 1].abs() < 1e-8, torch.full_like(d[:, 1], 1e-8), d[:, 1])
    t = torch.where(t > 1e-4, t, torch.full_like(t, float("inf")))

    hit_p = o + d * t.clamp(max=1e6)[:, None]
    tile = ((hit_p[:, 0].floor() + hit_p[:, 2].floor()) % 2.0).abs()
    shade = 0.32 + 0.30 * tile
    color = shade[:, None].repeat(1, 3)
    normal = torch.zeros_like(o)
    normal[:, 1] = 1.0
    return t, normal, color


def render(scene: Scene, cameras: Cameras, height: int, width: int) -> tuple[Tensor, Tensor]:
    """Render a scene from a batch of cameras.

    Returns ``(rgb, depth)`` with shapes ``(V, 3, H, W)`` in ``[-1, 1]`` and
    ``(V, H, W)`` of *z*-depth.  Rays that escape get the sky colour and a
    depth of zero, which the loader marks as invalid.
    """
    origins, dirs = cameras.rays(height, width)          # (V, H, W, 3)
    v = origins.shape[0]
    o = origins.reshape(-1, 3)
    d = dirs.reshape(-1, 3)

    hits = [_intersect_spheres(o, d, scene), _intersect_boxes(o, d, scene), _intersect_floor(o, d, scene)]
    t_all = torch.stack([h[0] for h in hits], dim=0)      # (3, N)
    n_all = torch.stack([h[1] for h in hits], dim=0)
    c_all = torch.stack([h[2] for h in hits], dim=0)

    best = t_all.argmin(dim=0)
    idx = best[None, :, None].expand(1, -1, 3)
    t = t_all.gather(0, best[None]).squeeze(0)
    normal = n_all.gather(0, idx).squeeze(0)
    albedo = c_all.gather(0, idx).squeeze(0)

    lambert = (normal * scene.light_dir[None]).sum(-1).clamp_min(0.0)
    color = albedo * (0.30 + 0.85 * lambert)[:, None]

    sky = torch.tensor([0.62, 0.72, 0.88], device=o.device).expand_as(color)
    miss = torch.isinf(t)
    color = torch.where(miss[:, None], sky, color.clamp(0.0, 1.0))

    # Convert ray distance to z-depth along the optical axis.
    fwd = cameras.c2w[:, :3, 2]                           # (V, 3)
    fwd = fwd[:, None, None, :].expand(v, height, width, 3).reshape(-1, 3)
    z = t * (d * fwd).sum(-1).clamp_min(1e-6)
    z = torch.where(miss, torch.zeros_like(z), z)

    rgb = color.reshape(v, height, width, 3).permute(0, 3, 1, 2) * 2.0 - 1.0
    return rgb, z.reshape(v, height, width)


def orbit_cameras(
    n_views: int,
    generator: torch.Generator,
    *,
    height: int,
    width: int,
    radius_range: tuple[float, float] = (3.0, 4.5),
    elevation_range: tuple[float, float] = (0.15, 0.85),
    fov_deg: float = 55.0,
    jitter: float = 0.25,
) -> Cameras:
    """Sample ``n_views`` cameras on a jittered arc looking at the origin.

    A *contiguous arc* rather than independent random views is what makes the
    sequence resemble a camera trajectory, so autoregressive rollout has a
    trajectory to learn.
    """
    start = float(torch.rand(1, generator=generator)) * 2.0 * math.pi
    span = float(torch.rand(1, generator=generator)) * math.pi + 0.6
    angles = start + torch.linspace(0.0, span, n_views)
    angles = angles + (torch.rand(n_views, generator=generator) - 0.5) * jitter

    radius = torch.rand(n_views, generator=generator) * (radius_range[1] - radius_range[0]) + radius_range[0]
    elev = torch.rand(n_views, generator=generator) * (elevation_range[1] - elevation_range[0]) + elevation_range[0]

    eye = torch.stack(
        (radius * angles.cos() * elev.cos(), radius * elev.sin(), radius * angles.sin() * elev.cos()), dim=-1
    )
    target = (torch.rand(n_views, 3, generator=generator) - 0.5) * 0.3
    target[:, 1] -= 0.3
    w2c = look_at(eye, target)

    f = 0.5 * width / math.tan(math.radians(fov_deg) * 0.5)
    k = torch.zeros(n_views, 3, 3)
    k[:, 0, 0] = f
    k[:, 1, 1] = f
    k[:, 0, 2] = width * 0.5
    k[:, 1, 2] = height * 0.5
    k[:, 2, 2] = 1.0
    return Cameras(w2c, k, height, width)


class SyntheticWorlds(Dataset):
    """A deterministic, on-the-fly dataset of posed multi-view scenes.

    Each item is a dict with ``image (V,3,H,W)``, ``depth (V,H,W)``,
    ``depth_valid (V,H,W)``, ``w2c (V,4,4)``, ``K (V,3,3)`` and ``caption``.
    Scenes are generated from the index, so the dataset is reproducible and
    needs no storage.
    """

    def __init__(
        self,
        length: int = 512,
        *,
        image_size: int = 64,
        views: int = 4,
        seed: int = 0,
        normalize_scale: bool = True,
    ):
        self.length = int(length)
        self.image_size = int(image_size)
        self.views = int(views)
        self.seed = int(seed)
        self.normalize_scale = normalize_scale

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> dict:
        if not 0 <= index < self.length:
            raise IndexError(index)
        g = torch.Generator().manual_seed(self.seed * 1_000_003 + index)

        scene = random_scene(g)
        cams = orbit_cameras(self.views, g, height=self.image_size, width=self.image_size)
        rgb, depth = render(scene, cams, self.image_size, self.image_size)

        if self.normalize_scale:
            centers = cams.centers
            scale = (centers - centers.mean(0, keepdim=True)).norm(dim=-1).mean().clamp_min(1e-6)
            c2w = cams.c2w.clone()
            c2w[:, :3, 3] = c2w[:, :3, 3] / scale
            from ..cameras import invert_rigid

            cams = Cameras(invert_rigid(c2w), cams.K, cams.height, cams.width)
            depth = depth / scale

        # The floor is an unbounded plane, so grazing rays run to the horizon
        # and land far beyond what the depth encoding can represent.  Those
        # pixels are still supervised (the clamp is a sensible "very far"
        # target) but they must not be scored: no prediction could match them.
        valid = (depth > 0) & (depth <= DEPTH_FAR)

        return {
            "image": rgb,
            "depth": depth,
            "depth_valid": valid,
            "w2c": cams.w2c,
            "K": cams.K,
            "caption": scene.caption,
        }
