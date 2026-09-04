"""Tests for the procedural renderer -- the ground truth everything is scored against."""

import math

import pytest
import torch

from atlas.cameras import Cameras, look_at, unproject_depth
from atlas.data import SyntheticWorlds, orbit_cameras, random_scene, render
from atlas.text import WordTokenizer


def test_dataset_item_shapes_and_ranges():
    ds = SyntheticWorlds(length=3, image_size=24, views=3, seed=5)
    item = ds[0]
    assert item["image"].shape == (3, 3, 24, 24)
    assert item["depth"].shape == (3, 24, 24)
    assert item["w2c"].shape == (3, 4, 4)
    assert item["K"].shape == (3, 3, 3)
    assert item["image"].min() >= -1.0 and item["image"].max() <= 1.0
    assert bool(item["depth_valid"].any())
    assert item["depth"][item["depth_valid"]].min() > 0


def test_dataset_is_deterministic():
    a = SyntheticWorlds(length=2, image_size=16, views=2, seed=7)[1]
    b = SyntheticWorlds(length=2, image_size=16, views=2, seed=7)[1]
    assert torch.equal(a["image"], b["image"])
    assert a["caption"] == b["caption"]


def test_different_seeds_give_different_scenes():
    a = SyntheticWorlds(length=2, image_size=16, views=2, seed=1)[0]
    b = SyntheticWorlds(length=2, image_size=16, views=2, seed=2)[0]
    assert not torch.equal(a["image"], b["image"])


def test_out_of_range_index_raises():
    ds = SyntheticWorlds(length=2, image_size=16, views=2)
    with pytest.raises(IndexError):
        ds[5]


def test_captions_are_inside_the_tokenizer_vocabulary():
    """A caption with unknown words would silently train on <unk>."""
    tok = WordTokenizer()
    ds = SyntheticWorlds(length=16, image_size=8, views=1, seed=3)
    for i in range(16):
        caption = ds[i]["caption"]
        ids = tok.encode(caption, 32)
        assert tok.unk_id not in ids.tolist(), f"unknown word in {caption!r}"


def test_renderer_depth_agrees_with_a_known_sphere():
    """A camera on the -z axis looking at a unit sphere at the origin."""
    scene = random_scene(torch.Generator().manual_seed(0))
    scene.sphere_centers = torch.zeros(1, 3)
    scene.sphere_radii = torch.tensor([1.0])
    scene.sphere_colors = torch.ones(1, 3)
    scene.box_lo = torch.zeros(0, 3)
    scene.box_hi = torch.zeros(0, 3)
    scene.box_colors = torch.zeros(0, 3)
    scene.floor_y = -50.0

    size = 33
    eye = torch.tensor([[0.0, 0.0, -5.0]])
    w2c = look_at(eye, torch.zeros(1, 3))
    f = 0.5 * size / math.tan(math.radians(60.0) * 0.5)
    k = torch.zeros(1, 3, 3)
    k[:, 0, 0] = k[:, 1, 1] = f
    k[:, 0, 2] = k[:, 1, 2] = size * 0.5
    k[:, 2, 2] = 1.0

    _, depth = render(scene, Cameras(w2c, k, size, size), size, size)
    # The centre ray hits the sphere's near pole: 5 - 1 = 4 away.
    assert pytest.approx(4.0, abs=0.05) == float(depth[0, size // 2, size // 2])


def test_unprojected_depth_is_consistent_across_views():
    """Two views of one scene must unproject onto the same surface."""
    ds = SyntheticWorlds(length=1, image_size=32, views=2, seed=11)
    item = ds[0]
    cams = Cameras(item["w2c"], item["K"], 32, 32)
    points = unproject_depth(cams, item["depth"])

    # Project view 0's points into view 1 and compare depth where both are valid.
    uv, z = cams[1:2].project(points[0].reshape(1, -1, 3))
    inside = (uv[..., 0] >= 0) & (uv[..., 0] < 32) & (uv[..., 1] >= 0) & (uv[..., 1] < 32) & (z > 0)
    assert bool(inside.any()), "the two views share no field of view"

    px = uv[0][inside[0]].long().clamp(0, 31)
    observed = item["depth"][1][px[:, 1], px[:, 0]]
    predicted = z[0][inside[0]]
    # Occlusion means predicted >= observed; agreement on the visible surface
    # is what matters, so check the median rather than the mean.
    ratio = (predicted / observed.clamp_min(1e-6)).median()
    assert pytest.approx(1.0, abs=0.15) == float(ratio)


def test_orbit_cameras_look_towards_the_origin():
    cams = orbit_cameras(6, torch.Generator().manual_seed(0), height=16, width=16)
    to_origin = torch.nn.functional.normalize(-cams.centers, dim=-1)
    forward = cams.c2w[:, :3, 2]
    assert bool(((to_origin * forward).sum(-1) > 0.8).all())
