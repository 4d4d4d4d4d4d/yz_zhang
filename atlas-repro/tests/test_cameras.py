"""Geometry tests: if these fail, nothing above them can be trusted."""

import math

import pytest
import torch

from atlas.cameras import (
    Cameras,
    invert_rigid,
    look_at,
    normalize_scene_scale,
    plucker_rays,
    unproject_depth,
)


def make_cameras(n=3, size=16, fov=60.0):
    g = torch.Generator().manual_seed(0)
    eye = torch.randn(n, 3, generator=g) * 2.0
    eye[:, 1] = eye[:, 1].abs() + 1.0
    w2c = look_at(eye, torch.zeros(n, 3))
    f = 0.5 * size / math.tan(math.radians(fov) * 0.5)
    k = torch.zeros(n, 3, 3)
    k[:, 0, 0] = k[:, 1, 1] = f
    k[:, 0, 2] = k[:, 1, 2] = size * 0.5
    k[:, 2, 2] = 1.0
    return Cameras(w2c, k, size, size)


def test_invert_rigid_is_an_inverse():
    cams = make_cameras()
    identity = cams.w2c @ invert_rigid(cams.w2c)
    assert torch.allclose(identity, torch.eye(4).expand_as(identity), atol=1e-5)


def test_look_at_produces_proper_rotations():
    """det = +1, not -1.

    Cross products taken in the wrong order give an orthonormal matrix that is
    a reflection.  Everything downstream stays self-consistent, so this is
    invisible until real posed data -- whose rotations are proper -- is mixed
    in.
    """
    cams = make_cameras(n=6)
    r = cams.w2c[:, :3, :3]
    assert torch.allclose(torch.linalg.det(r), torch.ones(6), atol=1e-5)
    identity = r @ r.transpose(-1, -2)
    assert torch.allclose(identity, torch.eye(3).expand_as(identity), atol=1e-5)


def test_camera_axes_are_right_handed():
    """x * y = z for the (right, down, forward) frame."""
    cams = make_cameras(n=4)
    r = cams.w2c[:, :3, :3]
    x, y, z = r[:, 0], r[:, 1], r[:, 2]
    assert torch.allclose(torch.cross(x, y, dim=-1), z, atol=1e-5)


def test_look_at_places_the_camera_where_asked():
    eye = torch.tensor([[3.0, 2.0, -1.0]])
    w2c = look_at(eye, torch.zeros(1, 3))
    assert torch.allclose(invert_rigid(w2c)[:, :3, 3], eye, atol=1e-5)


def test_look_at_points_the_optical_axis_at_the_target():
    eye = torch.tensor([[0.0, 0.0, -4.0]])
    target = torch.tensor([[1.0, 0.5, 0.0]])
    forward = invert_rigid(look_at(eye, target))[:, :3, 2]
    expected = torch.nn.functional.normalize(target - eye, dim=-1)
    assert torch.allclose(forward, expected, atol=1e-5)


def test_rays_are_unit_length_and_start_at_the_camera():
    cams = make_cameras()
    origins, dirs = cams.rays()
    assert torch.allclose(dirs.norm(dim=-1), torch.ones_like(dirs[..., 0]), atol=1e-5)
    assert torch.allclose(origins[:, 0, 0], cams.centers, atol=1e-5)


def test_plucker_moment_is_invariant_along_the_ray():
    """The whole reason Plucker is the right positional code for a ray."""
    o = torch.randn(8, 3)
    d = torch.nn.functional.normalize(torch.randn(8, 3), dim=-1)
    a = plucker_rays(o, d)
    b = plucker_rays(o + d * 3.7, d)
    assert torch.allclose(a, b, atol=1e-5)


def test_projection_inverts_unprojection():
    cams = make_cameras(n=2, size=12)
    depth = torch.rand(2, 12, 12) * 2.0 + 1.0
    points = unproject_depth(cams, depth)

    uv, z = cams.project(points.reshape(2, -1, 3))
    assert torch.allclose(z, depth.reshape(2, -1), atol=1e-4)

    from atlas.cameras import pixel_grid

    expected = pixel_grid(12, 12).reshape(-1, 2).expand(2, -1, 2)
    assert torch.allclose(uv, expected, atol=1e-3)


def test_rays_at_patch_resolution_cover_the_same_frustum():
    """Patch-centre rays must span the image, not a corner of it."""
    cams = make_cameras(n=1, size=16)
    _, coarse = cams.rays(4, 4)
    _, fine = cams.rays(16, 16)
    # The coarse grid's extremes should sit inside the fine grid's extremes.
    assert coarse.reshape(-1, 3).min() >= fine.reshape(-1, 3).min() - 1e-5
    assert coarse.reshape(-1, 3).max() <= fine.reshape(-1, 3).max() + 1e-5


def test_normalize_scene_scale_gives_unit_spread():
    cams = make_cameras(n=5)
    scaled, factor = normalize_scene_scale(cams)
    centers = scaled.centers
    spread = (centers - centers.mean(0, keepdim=True)).norm(dim=-1).mean()
    assert pytest.approx(1.0, abs=1e-4) == float(spread)
    assert float(factor) > 0


def test_cameras_reject_mismatched_batches():
    with pytest.raises(ValueError):
        Cameras(torch.eye(4).expand(3, 4, 4), torch.eye(3).expand(2, 3, 3), 8, 8)


def test_look_at_survives_an_up_vector_along_the_view_direction():
    """Straight down: the default up is parallel to the view, so the cross
    product would vanish without the degeneracy guard."""
    eye = torch.tensor([[0.0, 5.0, 0.0], [3.0, 1.0, 0.0]])
    w2c = look_at(eye, torch.zeros(2, 3))
    assert torch.isfinite(w2c).all()

    r = w2c[:, :3, :3]
    identity = r @ r.transpose(-1, -2)
    assert torch.allclose(identity, torch.eye(3).expand_as(identity), atol=1e-4)
    assert torch.allclose(torch.linalg.det(r), torch.ones(2), atol=1e-4)


def test_look_at_leaves_well_conditioned_cameras_alone():
    """Only degenerate rows should be perturbed, not the whole batch."""
    eye = torch.tensor([[0.0, 5.0, 0.0], [0.0, 0.0, -4.0]])
    mixed = look_at(eye, torch.zeros(2, 3))
    alone = look_at(eye[1:], torch.zeros(1, 3))
    assert torch.allclose(mixed[1], alone[0], atol=1e-6)
