"""Tests for the spatial context and its attention mask."""

import pytest
import torch

from atlas.cameras import Cameras
from atlas.spatial_context import (
    DEPTH,
    IMAGE,
    TEXT,
    Element,
    SpatialContext,
    block_causal_mask,
    build_attention_mask,
)


def dummy_cameras(batch=2, size=8):
    return Cameras(torch.eye(4).expand(batch, 4, 4).contiguous(), torch.eye(3).expand(batch, 3, 3).contiguous(), size, size)


def test_visual_elements_require_a_pose():
    with pytest.raises(ValueError, match="camera pose"):
        Element(IMAGE, torch.zeros(2, 3, 8, 8))


def test_camera_batch_must_match_data_batch():
    with pytest.raises(ValueError, match="camera batch"):
        Element(IMAGE, torch.zeros(4, 3, 8, 8), dummy_cameras(batch=2))


def test_context_rejects_ragged_batches():
    a = Element(TEXT, torch.zeros(2, 4, dtype=torch.long))
    b = Element(TEXT, torch.zeros(3, 4, dtype=torch.long))
    with pytest.raises(ValueError, match="inconsistent batch"):
        SpatialContext([a, b])


def test_block_causal_mask_is_lower_triangular_over_elements():
    ids = torch.tensor([0, 0, 1, 1, 2])
    mask = block_causal_mask(ids)
    # element 0 cannot see elements 1 or 2
    assert not bool(mask[0, 2:].any())
    # element 2 sees everything
    assert bool(mask[4].all())
    # tokens within element 1 see each other
    assert bool(mask[2, 3]) and bool(mask[3, 2])


def test_continuous_elements_attend_bidirectionally_within_themselves():
    ids = torch.tensor([0, 0, 0])
    pos = torch.tensor([0, 1, 2])
    mask = build_attention_mask(ids, pos, torch.tensor([False]))
    assert bool(mask.all())


def test_text_elements_attend_causally_within_themselves():
    ids = torch.tensor([0, 0, 0])
    pos = torch.tensor([0, 1, 2])
    mask = build_attention_mask(ids, pos, torch.tensor([True]))
    assert not bool(mask[0, 1]) and not bool(mask[0, 2])
    assert bool(mask[2, 0]) and bool(mask[2, 1])


def test_text_then_image_gives_text_prefix_conditioning():
    ids = torch.tensor([0, 0, 1, 1])
    pos = torch.tensor([0, 1, 0, 1])
    mask = build_attention_mask(ids, pos, torch.tensor([True, False]))
    # the image element sees the whole caption
    assert bool(mask[2, 0]) and bool(mask[2, 1])
    # the caption never sees the image
    assert not bool(mask[0, 2]) and not bool(mask[1, 3])


def test_observed_mask_and_replacement():
    cams = dummy_cameras()
    img = Element(IMAGE, torch.zeros(2, 3, 8, 8), cams, torch.tensor([True, False]))
    dep = Element(DEPTH, torch.zeros(2, 1, 8, 8), cams)
    ctx = SpatialContext([img, dep])

    assert ctx.observed_mask().shape == (2, 2)
    assert bool(ctx.observed_mask()[0, 0]) and not bool(ctx.observed_mask()[1, 0])

    replaced = ctx.replace_at(1, dep.with_data(torch.ones(2, 1, 8, 8)))
    assert float(replaced[1].data.sum()) > 0
    assert float(ctx[1].data.sum()) == 0  # the original is untouched


def test_indices_of_and_append():
    cams = dummy_cameras()
    ctx = SpatialContext([Element(TEXT, torch.zeros(2, 4, dtype=torch.long))])
    ctx = ctx.append(Element(IMAGE, torch.zeros(2, 3, 8, 8), cams))
    assert ctx.indices_of(TEXT) == [0]
    assert ctx.indices_of(IMAGE) == [1]
    assert len(ctx) == 2
