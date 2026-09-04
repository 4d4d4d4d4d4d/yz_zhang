"""The spatial context: Atlas' unified multimodal sequence.

Atlas does not have separate encoders for "input views", "target views" and
"text".  Everything is folded into a single ordered sequence of *elements*,
and every visual element is grounded at an explicit 3D pose.  Generation is
autoregressive over elements and diffusive within them, so the same context
expresses reconstruction, novel-view synthesis and video rollout depending
only on which elements are observed and which are noise.

An element is one of:

``text``   a block of discrete tokens (the prompt / caption).
``image``  an RGB frame anchored by a camera pose.
``depth``  a depth map anchored by a camera pose (unprojects to a pointmap).

Every element carries its own diffusion timestep.  Observed elements sit at
``t = 1`` (clean), elements being generated are noised independently.  That
per-element timestep is what lets one trained model roll out frame by frame,
denoise a whole clip jointly, or infer depth for views it has already seen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import torch
from torch import Tensor

from .cameras import Cameras

__all__ = ["Element", "SpatialContext", "TEXT", "IMAGE", "DEPTH", "MODALITIES", "block_causal_mask"]

TEXT = "text"
IMAGE = "image"
DEPTH = "depth"
MODALITIES = (TEXT, IMAGE, DEPTH)

#: Modalities carried by the rectified-flow (continuous) branch of the model.
CONTINUOUS = (IMAGE, DEPTH)


@dataclass
class Element:
    """One entry of the spatial context.

    Attributes
    ----------
    kind:
        One of :data:`MODALITIES`.
    data:
        ``(B, L)`` int64 token ids for ``text``; ``(B, C, H, W)`` float for
        ``image`` (RGB in ``[-1, 1]``) and ``depth`` (``(B, 1, H, W)``, in
        normalised scene units).
    cameras:
        Pose anchoring this element in 3D.  Required for visual elements,
        ``None`` for text.  Batch shape must be ``(B,)``.
    observed:
        ``(B,)`` bool.  ``True`` means the element is given as context and is
        never noised or supervised; ``False`` means it is a generation target.
    t:
        ``(B,)`` float in ``[0, 1]``, the rectified-flow time of this element
        (``1`` = clean data, ``0`` = pure noise).  Filled in by the trainer or
        the sampler; ``None`` on freshly constructed elements.
    """

    kind: str
    data: Tensor
    cameras: Cameras | None = None
    observed: Tensor | None = None
    t: Tensor | None = None

    def __post_init__(self) -> None:
        if self.kind not in MODALITIES:
            raise ValueError(f"unknown element kind {self.kind!r}")
        if self.kind in CONTINUOUS and self.cameras is None:
            raise ValueError(f"{self.kind} elements must carry a camera pose")
        if self.cameras is not None and tuple(self.cameras.batch_shape) != (self.batch_size,):
            raise ValueError(
                f"camera batch {tuple(self.cameras.batch_shape)} does not match data batch {self.batch_size}"
            )
        if self.observed is None:
            self.observed = torch.zeros(self.batch_size, dtype=torch.bool, device=self.data.device)

    @property
    def batch_size(self) -> int:
        return int(self.data.shape[0])

    @property
    def is_continuous(self) -> bool:
        return self.kind in CONTINUOUS

    @property
    def spatial_shape(self) -> tuple[int, int]:
        if not self.is_continuous:
            raise AttributeError("text elements have no spatial shape")
        return int(self.data.shape[-2]), int(self.data.shape[-1])

    def to(self, *args, **kwargs) -> "Element":
        return replace(
            self,
            data=self.data.to(*args, **kwargs),
            cameras=None if self.cameras is None else self.cameras.to(*args, **kwargs),
            observed=self.observed.to(kwargs.get("device", self.observed.device)),
            t=None if self.t is None else self.t.to(*args, **kwargs),
        )

    def with_data(self, data: Tensor) -> "Element":
        return replace(self, data=data)


class SpatialContext:
    """An ordered, batched sequence of :class:`Element` objects.

    All elements share a batch size and element *structure* across the batch
    (the same kinds in the same order), which is what allows the whole context
    to be packed into one padded-free token sequence.
    """

    def __init__(self, elements: Sequence[Element]):
        elements = list(elements)
        if not elements:
            raise ValueError("a spatial context needs at least one element")
        sizes = {e.batch_size for e in elements}
        if len(sizes) != 1:
            raise ValueError(f"inconsistent batch sizes across elements: {sorted(sizes)}")
        self.elements = elements

    # -- container protocol ---------------------------------------------
    def __len__(self) -> int:
        return len(self.elements)

    def __iter__(self) -> Iterable[Element]:
        return iter(self.elements)

    def __getitem__(self, i: int) -> Element:
        return self.elements[i]

    @property
    def batch_size(self) -> int:
        return self.elements[0].batch_size

    @property
    def device(self):
        return self.elements[0].data.device

    def to(self, *args, **kwargs) -> "SpatialContext":
        return SpatialContext([e.to(*args, **kwargs) for e in self.elements])

    def kinds(self) -> list[str]:
        return [e.kind for e in self.elements]

    def indices_of(self, kind: str) -> list[int]:
        return [i for i, e in enumerate(self.elements) if e.kind == kind]

    def replace_at(self, index: int, element: Element) -> "SpatialContext":
        out = list(self.elements)
        out[index] = element
        return SpatialContext(out)

    def append(self, element: Element) -> "SpatialContext":
        return SpatialContext([*self.elements, element])

    def observed_mask(self) -> Tensor:
        """``(B, n_elements)`` bool of which elements are context."""
        return torch.stack([e.observed for e in self.elements], dim=1)

    def cameras(self) -> Cameras | None:
        """Stack the poses of all visual elements into ``(B, n_visual)``."""
        vis = [e for e in self.elements if e.is_continuous]
        if not vis:
            return None
        w2c = torch.stack([e.cameras.w2c for e in vis], dim=1)
        k = torch.stack([e.cameras.K for e in vis], dim=1)
        return Cameras(w2c, k, vis[0].cameras.height, vis[0].cameras.width)


def block_causal_mask(element_ids: Tensor, *, num_elements: int | None = None) -> Tensor:
    """Attention mask for "autoregressive across elements, dense within".

    ``element_ids`` is ``(S,)`` giving each token's element index.  The result
    is ``(S, S)`` boolean where ``True`` means *allowed to attend*.  Token
    ``i`` sees every token whose element index is ``<=`` its own, so an
    element is generated conditioned on all earlier elements while its own
    tokens are denoised jointly and bidirectionally.
    """
    if element_ids.ndim != 1:
        raise ValueError(f"element_ids must be 1-D, got {tuple(element_ids.shape)}")
    if num_elements is not None and int(element_ids.max()) >= num_elements:
        raise ValueError("element_ids contains an index beyond num_elements")
    return element_ids[None, :] <= element_ids[:, None]


def build_attention_mask(
    element_ids: Tensor,
    token_positions: Tensor,
    causal_within: Tensor,
) -> Tensor:
    """Full Atlas attention mask.

    Across elements the mask is causal: element ``k`` sees elements ``<= k``.
    *Within* an element the behaviour depends on the modality:

    * continuous elements (image, depth) attend bidirectionally, because their
      tokens are denoised jointly by the flow;
    * text elements attend causally, because their tokens are sampled one at
      a time from a categorical distribution.

    Parameters
    ----------
    element_ids:
        ``(S,)`` element index of every token.
    token_positions:
        ``(S,)`` index of every token *within* its element.
    causal_within:
        ``(n_elements,)`` bool -- whether that element is causal internally.

    Returns
    -------
    ``(S, S)`` bool tensor, ``True`` where attention is permitted.
    """
    if element_ids.shape != token_positions.shape:
        raise ValueError("element_ids and token_positions must have the same shape")

    across = element_ids[None, :] <= element_ids[:, None]
    same = element_ids[None, :] == element_ids[:, None]
    earlier_token = token_positions[None, :] <= token_positions[:, None]

    row_is_causal = causal_within.to(element_ids.device)[element_ids][:, None]
    # Inside a causal element, drop attention to later tokens of that element.
    return across & (~(same & row_is_causal) | earlier_token)
