"""Tests for PLY export, depth coding and metrics."""

import struct

import pytest
import torch

from atlas.depth_repr import DEPTH_FAR, decode_depth, encode_depth
from atlas.export import points_from_context, write_gaussian_splat_ply, write_point_cloud_ply
from atlas.imageio import colorize_depth, save_grid, save_png, to_uint8
from atlas.metrics import abs_rel, align_scale, chamfer_distance, delta_accuracy, psnr


def test_depth_coding_roundtrips():
    d = torch.rand(4, 8, 8) * 10.0 + 0.05
    assert torch.allclose(decode_depth(encode_depth(d)), d, atol=1e-3)


def test_depth_code_is_bounded():
    d = torch.tensor([0.0, 1e-4, 1.0, DEPTH_FAR, DEPTH_FAR * 10])
    code = encode_depth(d)
    assert code.min() >= -1.0 and code.max() <= 1.0


def test_point_cloud_ply_has_the_right_vertex_count():
    pts = torch.randn(50, 3)
    rgb = torch.rand(50, 3) * 2 - 1
    path = write_point_cloud_ply("/tmp/atlas_test_pc.ply", pts, rgb)
    header = path.read_bytes().split(b"end_header\n")[0].decode()
    assert "element vertex 50" in header
    assert "property uchar red" in header


def test_point_cloud_rejects_mismatched_colours():
    with pytest.raises(ValueError):
        write_point_cloud_ply("/tmp/atlas_test_bad.ply", torch.randn(10, 3), torch.randn(4, 3))


def test_splat_ply_carries_the_expected_properties():
    pts = torch.randn(12, 3)
    rgb = torch.rand(12, 3) * 2 - 1
    path = write_gaussian_splat_ply("/tmp/atlas_test_splat.ply", pts, rgb, scale=0.03)
    header = path.read_bytes().split(b"end_header\n")[0].decode()
    for prop in ("f_dc_0", "opacity", "scale_0", "rot_0"):
        assert f"property float {prop}" in header
    assert "element vertex 12" in header


def test_splat_positions_survive_the_roundtrip():
    pts = torch.randn(5, 3)
    path = write_gaussian_splat_ply("/tmp/atlas_test_splat2.ply", pts, torch.zeros(5, 3))
    body = path.read_bytes().split(b"end_header\n", 1)[1]
    stride = 17 * 4  # 17 float32 properties per vertex
    first = struct.unpack("<fff", body[:12])
    assert torch.allclose(torch.tensor(first), pts[0], atol=1e-5)
    assert len(body) == 5 * stride


def test_points_from_context_drops_far_points():
    points = torch.randn(2, 4, 4, 3)
    images = torch.rand(2, 3, 4, 4) * 2 - 1
    depth = torch.full((2, 4, 4), 100.0)
    depth[0, 0, 0] = 1.0
    pts, rgb = points_from_context(points, images, depth=depth, max_depth=10.0)
    assert pts.shape == (1, 3) and rgb.shape == (1, 3)


def test_points_from_context_rejects_misaligned_views():
    with pytest.raises(ValueError, match="pointmaps but"):
        points_from_context(torch.randn(3, 4, 4, 3), torch.randn(2, 3, 4, 4))


def test_psnr_is_infinite_for_a_perfect_match():
    x = torch.rand(2, 3, 8, 8) * 2 - 1
    assert float(psnr(x, x).min()) > 100


def test_abs_rel_is_zero_when_depth_matches_up_to_scale():
    d = torch.rand(2, 8, 8) + 0.5
    assert float(abs_rel(d * 3.0, d).max()) == pytest.approx(0.0, abs=1e-4)


def test_align_scale_recovers_a_known_factor():
    d = torch.rand(1, 6, 6) + 1.0
    assert float(align_scale(d, d * 2.5)[0]) == pytest.approx(2.5, abs=1e-4)


def test_delta_accuracy_is_one_for_a_perfect_match():
    d = torch.rand(2, 8, 8) + 0.5
    assert float(delta_accuracy(d, d).min()) == pytest.approx(1.0, abs=1e-6)


def test_chamfer_is_zero_for_identical_clouds():
    a = torch.randn(1, 64, 3)
    assert float(chamfer_distance(a, a.clone())) == pytest.approx(0.0, abs=1e-5)


def test_png_writing_and_conversion():
    img = torch.rand(3, 9, 7) * 2 - 1
    assert to_uint8(img).shape == (9, 7, 3)
    path = save_png("/tmp/atlas_test.png", img)
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    save_grid("/tmp/atlas_test_grid.png", torch.rand(5, 3, 8, 8) * 2 - 1, columns=3)


def test_colorize_depth_handles_an_empty_mask():
    out = colorize_depth(torch.zeros(4, 4))
    assert out.shape == (1, 4, 4) and float(out.max()) <= 0.0
