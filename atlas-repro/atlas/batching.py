"""Turning dataloader batches into spatial contexts.

This is where the training curriculum lives.  A batch of posed frames becomes
a sequence

    [caption] [image_0] [depth_0] [image_1] [depth_1] ...

in which the first ``n_observed`` views are marked as context and the rest are
generation targets.  Randomising ``n_observed`` per batch is what teaches one
set of weights to do reconstruction (many views observed), novel-view
synthesis (a few) and text-to-world generation (none).
"""

from __future__ import annotations

import torch
from torch import Tensor

from .cameras import Cameras
from .spatial_context import DEPTH, IMAGE, TEXT, Element, SpatialContext
from .text import WordTokenizer

__all__ = ["build_context", "collate", "null_text_context"]


def collate(items: list[dict]) -> dict:
    """Stack dataset items, keeping captions as a list of strings."""
    out: dict = {}
    for key in items[0]:
        values = [item[key] for item in items]
        out[key] = values if isinstance(values[0], str) else torch.stack(values)
    return out


def build_context(
    batch: dict,
    tokenizer: WordTokenizer,
    *,
    n_observed: int,
    predict_depth: bool = True,
    with_text: bool = True,
    max_text_len: int = 32,
    max_views: int | None = None,
    device=None,
) -> SpatialContext:
    """Assemble the spatial context for one batch of posed frames.

    Parameters
    ----------
    n_observed:
        How many leading views are given as clean context.  ``0`` yields pure
        text-to-world generation; ``V`` yields pure depth reconstruction.
    """
    images: Tensor = batch["image"]
    if images.ndim != 5:
        raise ValueError(f"expected image of shape (B,V,3,H,W), got {tuple(images.shape)}")
    b, v = images.shape[:2]
    if not 0 <= n_observed <= v:
        raise ValueError(f"n_observed must be in [0, {v}], got {n_observed}")
    if max_views is not None and v > max_views:
        raise ValueError(
            f"batch has {v} views but the model config allows {max_views}; "
            "raise model.max_views or lower train.views_per_sample"
        )

    device = device or images.device
    images = images.to(device)
    depth = batch["depth"].to(device)
    w2c = batch["w2c"].to(device)
    k = batch["K"].to(device)
    height, width = images.shape[-2:]

    elements: list[Element] = []
    if with_text:
        ids = tokenizer.encode_batch(batch["caption"], max_text_len).to(device)
        observed = torch.ones(b, dtype=torch.bool, device=device)
        elements.append(Element(TEXT, ids, observed=observed))

    for i in range(v):
        cam = Cameras(w2c[:, i], k[:, i], height, width)
        obs = torch.full((b,), i < n_observed, dtype=torch.bool, device=device)
        elements.append(Element(IMAGE, images[:, i], cam, obs.clone()))
        if predict_depth:
            # Depth is always a target: predicting it for observed views is
            # exactly the 3D-reconstruction task.
            elements.append(
                Element(
                    DEPTH,
                    depth[:, i][:, None],
                    cam,
                    torch.zeros(b, dtype=torch.bool, device=device),
                )
            )
    return SpatialContext(elements)


def null_text_context(context: SpatialContext, tokenizer: WordTokenizer) -> SpatialContext:
    """Copy of ``context`` with the caption blanked, for classifier-free guidance."""
    idx = context.indices_of(TEXT)
    if not idx:
        return context
    el = context[idx[0]]
    null = tokenizer.null_prompt(el.batch_size, el.data.shape[1], device=el.data.device)
    return context.replace_at(idx[0], el.with_data(null))
