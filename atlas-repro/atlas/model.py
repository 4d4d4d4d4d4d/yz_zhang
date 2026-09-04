"""``AtlasModel`` -- a multimodal autoregressive diffusion transformer.

The model consumes a :class:`~atlas.spatial_context.SpatialContext` and
predicts every element of it at once:

* image and depth elements are predicted as rectified-flow *velocities* in
  latent space,
* text elements are predicted as categorical logits.

Because each element carries its own timestep, one forward pass covers all of
the regimes Atlas is asked to work in.  Freeze the first views at ``t = 1``
and noise the rest and you get camera-controlled generation; feed images and
noise only the depth elements and you get 3D reconstruction; noise a whole
trajectory and you get joint video denoising.  Nothing about the architecture
changes between these -- only which elements are observed.
"""

from __future__ import annotations

import math
from typing import Sequence

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .cameras import Cameras, unproject_depth
from .config import AtlasConfig
from .depth_repr import decode_depth, encode_depth
from .flow import flow_loss, interpolate, sample_timesteps, shift_timesteps, timestep_grid
from .spatial_context import DEPTH, IMAGE, MODALITIES, TEXT, Element, SpatialContext, build_attention_mask
from .tokenizer import ImageVAE, build_tokenizer
from .transformer import TimestepEmbedding, Transformer

__all__ = ["AtlasModel", "AtlasOutput", "patchify", "unpatchify", "fourier_features"]

_MODALITY_INDEX = {kind: i for i, kind in enumerate(MODALITIES)}


def patchify(x: Tensor, patch: int) -> Tensor:
    """``(B, C, H, W)`` -> ``(B, H/p * W/p, C * p * p)``."""
    b, c, h, w = x.shape
    if h % patch or w % patch:
        raise ValueError(f"({h}, {w}) not divisible by patch size {patch}")
    x = x.reshape(b, c, h // patch, patch, w // patch, patch)
    x = x.permute(0, 2, 4, 1, 3, 5)  # B, gh, gw, C, p, p
    return x.reshape(b, (h // patch) * (w // patch), c * patch * patch)


def unpatchify(tokens: Tensor, patch: int, channels: int, grid_h: int, grid_w: int) -> Tensor:
    """Inverse of :func:`patchify`."""
    b, n, d = tokens.shape
    if n != grid_h * grid_w:
        raise ValueError(f"token count {n} != {grid_h}x{grid_w}")
    if d != channels * patch * patch:
        raise ValueError(f"token dim {d} != {channels} * {patch}^2")
    x = tokens.reshape(b, grid_h, grid_w, channels, patch, patch)
    x = x.permute(0, 3, 1, 4, 2, 5)
    return x.reshape(b, channels, grid_h * patch, grid_w * patch)


def fourier_features(x: Tensor, bands: int) -> Tensor:
    """Concatenate ``x`` with ``sin``/``cos`` at ``bands`` octaves."""
    if bands <= 0:
        return x
    freqs = 2.0 ** torch.arange(bands, device=x.device, dtype=x.dtype) * math.pi
    scaled = x[..., None] * freqs
    return torch.cat((x, scaled.sin().flatten(-2), scaled.cos().flatten(-2)), dim=-1)


class AtlasOutput:
    """Per-element predictions returned by :meth:`AtlasModel.forward`."""

    def __init__(self, elements: Sequence[Tensor], kinds: Sequence[str]):
        self.elements = list(elements)
        self.kinds = list(kinds)

    def __len__(self) -> int:
        return len(self.elements)

    def __getitem__(self, i: int) -> Tensor:
        return self.elements[i]

    def of_kind(self, kind: str) -> list[Tensor]:
        return [e for e, k in zip(self.elements, self.kinds) if k == kind]


class AtlasModel(nn.Module):
    def __init__(self, config: AtlasConfig):
        super().__init__()
        self.config = config
        cfg = config

        if cfg.tokenizer == "identity":
            self.tokenizer = build_tokenizer("identity", channels=3)
        else:
            self.tokenizer = build_tokenizer(
                "vae",
                in_channels=3,
                latent_channels=cfg.latent_channels,
                base_channels=cfg.vae_base_channels,
                downsample=cfg.vae_downsample,
                scaling_factor=cfg.vae_scaling_factor,
            )

        p = cfg.patch_size
        pd = cfg.depth_patch_size

        # -- input projections --
        self.image_in = nn.Linear(cfg.latent_channels * p * p, cfg.dim)
        self.depth_in = nn.Linear(pd * pd, cfg.dim)
        self.text_in = nn.Embedding(cfg.text_vocab_size, cfg.dim)
        self.modality_embed = nn.Embedding(len(MODALITIES), cfg.dim)

        # Plucker rays are what anchor a visual token at a place in the world.
        if cfg.use_plucker:
            ray_dim = 6 * (2 * cfg.plucker_bands + 1)
            self.ray_in = nn.Linear(ray_dim, cfg.dim)
        else:
            self.ray_in = None

        self.t_embed = TimestepEmbedding(cfg.dim)
        self.transformer = Transformer(cfg.dim, cfg.depth, cfg.n_heads, cfg.hidden_mult, rope_axes=3)

        # -- output heads --
        self.image_out = nn.Linear(cfg.dim, cfg.latent_channels * p * p)
        self.depth_out = nn.Linear(cfg.dim, pd * pd)
        self.text_out = nn.Linear(cfg.dim, cfg.text_vocab_size)
        for head in (self.image_out, self.depth_out):
            nn.init.zeros_(head.weight)
            nn.init.zeros_(head.bias)

    # ------------------------------------------------------------------
    # geometry / grids
    # ------------------------------------------------------------------
    @property
    def device(self):
        return self.image_in.weight.device

    def _grid_for(self, element: Element) -> tuple[int, int, int]:
        """Return ``(patch, grid_h, grid_w)`` for a continuous element."""
        h, w = element.spatial_shape
        patch = self.config.patch_size if element.kind == IMAGE else self.config.depth_patch_size
        if h % patch or w % patch:
            raise ValueError(f"{element.kind} of size {h}x{w} is not divisible by patch {patch}")
        return patch, h // patch, w // patch

    def _ray_tokens(self, element: Element, grid_h: int, grid_w: int) -> Tensor | None:
        if self.ray_in is None:
            return None
        plucker = element.cameras.plucker(grid_h, grid_w)  # (B, gh, gw, 6)
        feats = fourier_features(plucker, self.config.plucker_bands)
        return self.ray_in(feats.reshape(feats.shape[0], grid_h * grid_w, -1))

    # ------------------------------------------------------------------
    # embedding
    # ------------------------------------------------------------------
    def embed(self, context: SpatialContext) -> tuple[Tensor, Tensor, Tensor, Tensor, list[tuple[int, int]]]:
        """Pack a context into tokens, conditioning, positions and a mask.

        Returns ``(tokens, cond, positions, mask, spans)`` where ``spans`` maps
        element index to its ``(start, end)`` slice of the token sequence.
        """
        tokens: list[Tensor] = []
        conds: list[Tensor] = []
        positions: list[Tensor] = []
        element_ids: list[Tensor] = []
        token_pos: list[Tensor] = []
        causal_within: list[bool] = []
        spans: list[tuple[int, int]] = []

        device = context.device
        cursor = 0

        for idx, element in enumerate(context):
            if element.is_continuous:
                patch, gh, gw = self._grid_for(element)
                n = gh * gw
                flat = patchify(element.data, patch)
                proj = self.image_in if element.kind == IMAGE else self.depth_in
                tok = proj(flat)

                rays = self._ray_tokens(element, gh, gw)
                if rays is not None:
                    tok = tok + rays

                rows = torch.arange(gh, device=device).repeat_interleave(gw)
                cols = torch.arange(gw, device=device).repeat(gh)
                pos = torch.stack(
                    (torch.full((n,), idx, device=device, dtype=torch.long), rows, cols), dim=-1
                )
                causal_within.append(False)
            else:
                n = int(element.data.shape[1])
                tok = self.text_in(element.data)
                seq = torch.arange(n, device=device)
                pos = torch.stack(
                    (
                        torch.full((n,), idx, device=device, dtype=torch.long),
                        torch.zeros(n, device=device, dtype=torch.long),
                        seq,
                    ),
                    dim=-1,
                )
                causal_within.append(True)

            tok = tok + self.modality_embed.weight[_MODALITY_INDEX[element.kind]]

            t = element.t
            if t is None:
                t = torch.ones(element.batch_size, device=device, dtype=tok.dtype)
            cond = self.t_embed(t)[:, None, :].expand(-1, n, -1)

            tokens.append(tok)
            conds.append(cond)
            positions.append(pos)
            element_ids.append(torch.full((n,), idx, device=device, dtype=torch.long))
            token_pos.append(torch.arange(n, device=device))
            spans.append((cursor, cursor + n))
            cursor += n

        mask = build_attention_mask(
            torch.cat(element_ids),
            torch.cat(token_pos),
            torch.tensor(causal_within, device=device, dtype=torch.bool),
        )
        return (
            torch.cat(tokens, dim=1),
            torch.cat(conds, dim=1),
            torch.cat(positions, dim=0),
            mask,
            spans,
        )

    # ------------------------------------------------------------------
    # forward
    # ------------------------------------------------------------------
    def forward(self, context: SpatialContext) -> AtlasOutput:
        """Predict every element of ``context`` in one pass.

        Continuous elements must already hold *noisy latents* and their
        rectified-flow time in ``Element.t``.
        """
        tokens, cond, positions, mask, spans = self.embed(context)
        hidden = self.transformer(tokens, cond, positions=positions, mask=mask)

        outputs: list[Tensor] = []
        for element, (start, end) in zip(context, spans):
            h = hidden[:, start:end]
            if element.kind == TEXT:
                outputs.append(self.text_out(h))
                continue
            patch, gh, gw = self._grid_for(element)
            channels = self.config.latent_channels if element.kind == IMAGE else 1
            head = self.image_out if element.kind == IMAGE else self.depth_out
            outputs.append(unpatchify(head(h), patch, channels, gh, gw))
        return AtlasOutput(outputs, context.kinds())

    # ------------------------------------------------------------------
    # encoding / decoding of raw modalities
    # ------------------------------------------------------------------
    @torch.no_grad()
    def encode_context(self, context: SpatialContext) -> SpatialContext:
        """Map pixel-space RGB to tokenizer latents and metric depth to codes."""
        out = []
        for element in context:
            if element.kind == IMAGE:
                out.append(element.with_data(self.tokenizer.encode(element.data)))
            elif element.kind == DEPTH:
                out.append(element.with_data(encode_depth(element.data)))
            else:
                out.append(element)
        return SpatialContext(out)

    @torch.no_grad()
    def decode_image(self, latent: Tensor) -> Tensor:
        return self.tokenizer.decode(latent).clamp(-1.0, 1.0)

    @torch.no_grad()
    def decode_depth_map(self, code: Tensor) -> Tensor:
        return decode_depth(code)

    # ------------------------------------------------------------------
    # training
    # ------------------------------------------------------------------
    def add_noise(
        self,
        context: SpatialContext,
        *,
        distribution: str = "logit_normal",
        shift: float = 1.0,
        generator: torch.Generator | None = None,
    ) -> tuple[SpatialContext, dict[int, tuple[Tensor, Tensor]]]:
        """Noise every unobserved continuous element with its own timestep.

        Observed elements are pinned at ``t = 1`` and left untouched, which is
        precisely how a context frame differs from a target frame.
        """
        noised: list[Element] = []
        targets: dict[int, tuple[Tensor, Tensor]] = {}

        for idx, element in enumerate(context):
            if not element.is_continuous:
                noised.append(element)
                continue

            b = element.batch_size
            device = element.data.device
            t = sample_timesteps(
                b,
                device=device,
                dtype=element.data.dtype,
                distribution=distribution,
                generator=generator,
            )
            t = shift_timesteps(t, shift)
            # Observed elements are clean by definition.
            t = torch.where(element.observed, torch.ones_like(t), t)

            noise = torch.randn(
                element.data.shape, device=device, dtype=element.data.dtype, generator=generator
            )
            x_t = interpolate(element.data, noise, t)
            x_t = torch.where(element.observed.reshape(-1, 1, 1, 1), element.data, x_t)

            targets[idx] = (element.data, noise)
            noised.append(Element(element.kind, x_t, element.cameras, element.observed, t))

        return SpatialContext(noised), targets

    def compute_loss(
        self,
        context: SpatialContext,
        *,
        depth_weight: float = 1.0,
        text_weight: float = 0.1,
        distribution: str = "logit_normal",
        shift: float = 1.0,
        generator: torch.Generator | None = None,
    ) -> tuple[Tensor, dict[str, float]]:
        """Full training objective on a *latent-space* context."""
        noisy, targets = self.add_noise(
            context, distribution=distribution, shift=shift, generator=generator
        )
        pred = self.forward(noisy)

        losses: dict[str, list[Tensor]] = {IMAGE: [], DEPTH: [], TEXT: []}
        for idx, element in enumerate(noisy):
            if element.is_continuous:
                x1, noise = targets[idx]
                # Only generation targets are supervised.
                weight = (~element.observed).to(x1.dtype)
                if weight.sum() == 0:
                    continue
                losses[element.kind].append(flow_loss(pred[idx], x1, noise, weight))
            else:
                # Causal within the element: position i predicts token i+1.
                # Padding is excluded -- captions are short relative to the
                # padded length, and predicting <pad> is free accuracy that
                # would otherwise dominate the loss.
                logits = pred[idx][:, :-1]
                labels = element.data[:, 1:]
                text_loss = F.cross_entropy(
                    logits.reshape(-1, logits.shape[-1]),
                    labels.reshape(-1),
                    ignore_index=self.config.text_pad_id,
                )
                if torch.isfinite(text_loss):
                    losses[TEXT].append(text_loss)

        zero = torch.zeros((), device=self.device)
        image_loss = torch.stack(losses[IMAGE]).mean() if losses[IMAGE] else zero
        depth_loss = torch.stack(losses[DEPTH]).mean() if losses[DEPTH] else zero
        text_loss = torch.stack(losses[TEXT]).mean() if losses[TEXT] else zero

        total = image_loss + depth_weight * depth_loss + text_weight * text_loss
        stats = {
            "loss": float(total.detach()),
            "loss_image": float(image_loss.detach()),
            "loss_depth": float(depth_loss.detach()),
            "loss_text": float(text_loss.detach()),
        }
        return total, stats

    # ------------------------------------------------------------------
    # sampling
    # ------------------------------------------------------------------
    def _velocity_for(
        self,
        context: SpatialContext,
        target_indices: Sequence[int],
        guidance: float,
        uncond_fn,
    ):
        """Build a ``velocity_fn`` that denoises ``target_indices`` jointly.

        ``uncond_fn`` maps the *current* context to its unconditional twin.
        Deriving it per call rather than holding a second context alongside
        keeps the two branches sharing every already-generated view -- with a
        stale copy, guidance would drift further off with each new frame.
        """

        def fill(ctx: SpatialContext, x_flat: list[Tensor], t: Tensor) -> SpatialContext:
            for x, idx in zip(x_flat, target_indices):
                el = ctx[idx]
                ctx = ctx.replace_at(idx, Element(el.kind, x, el.cameras, el.observed, t))
            return ctx

        def velocity_fn(x_flat: list[Tensor], t: Tensor) -> list[Tensor]:
            out = self.forward(fill(context, x_flat, t))
            v = [out[idx] for idx in target_indices]

            if guidance != 1.0 and uncond_fn is not None:
                uout = self.forward(fill(uncond_fn(context), x_flat, t))
                v = [uv + guidance * (cv - uv) for cv, uv in zip(v, (uout[i] for i in target_indices))]
            return v

        return velocity_fn

    @torch.no_grad()
    def denoise_elements(
        self,
        context: SpatialContext,
        target_indices: Sequence[int],
        *,
        steps: int = 32,
        shift: float = 1.0,
        guidance: float = 1.0,
        uncond_fn=None,
        generator: torch.Generator | None = None,
    ) -> SpatialContext:
        """Jointly denoise the given elements from pure noise to data.

        ``uncond_fn``, when given alongside ``guidance != 1``, maps a context
        to its unconditional twin for classifier-free guidance.
        """
        target_indices = list(target_indices)
        if not target_indices:
            return context

        device = context.device
        xs = []
        for idx in target_indices:
            el = context[idx]
            if not el.is_continuous:
                raise ValueError("only image/depth elements can be denoised")
            xs.append(
                torch.randn(el.data.shape, device=device, dtype=el.data.dtype, generator=generator)
            )

        velocity_fn = self._velocity_for(context, target_indices, guidance, uncond_fn)
        grid = timestep_grid(steps, shift=shift, device=device, dtype=xs[0].dtype)

        for i in range(steps):
            t_now, t_next = grid[i], grid[i + 1]
            t_batch = t_now.expand(context.batch_size).to(xs[0].dtype)
            vs = velocity_fn(xs, t_batch)
            xs = [x + (t_next - t_now) * v for x, v in zip(xs, vs)]

        out = context
        for x, idx in zip(xs, target_indices):
            el = out[idx]
            ones = torch.ones(el.batch_size, device=device, dtype=x.dtype)
            observed = torch.ones(el.batch_size, dtype=torch.bool, device=device)
            out = out.replace_at(idx, Element(el.kind, x, el.cameras, observed, ones))
        return out

    @torch.no_grad()
    def generate_views(
        self,
        context: SpatialContext,
        cameras: Cameras,
        *,
        steps: int = 32,
        with_depth: bool | None = None,
        shift: float = 1.0,
        guidance: float = 1.0,
        uncond_fn=None,
        generator: torch.Generator | None = None,
    ) -> SpatialContext:
        """Autoregressively generate new views at the requested poses.

        ``cameras`` has batch shape ``(B, V)``.  Each view is appended to the
        context and denoised conditioned on everything generated so far, which
        is what keeps a long camera trajectory consistent with itself.
        """
        with_depth = self.config.predict_depth if with_depth is None else with_depth
        cfg = self.config
        b = context.batch_size
        n_views = int(cameras.batch_shape[1])
        device = context.device
        latent = cfg.latent_size

        for v in range(n_views):
            cam = cameras[:, v]
            placeholder = torch.zeros(b, cfg.latent_channels, latent, latent, device=device)
            context = context.append(Element(IMAGE, placeholder, cam))
            targets = [len(context) - 1]

            if with_depth:
                d = torch.zeros(b, 1, cfg.image_size, cfg.image_size, device=device)
                context = context.append(Element(DEPTH, d, cam))
                targets.append(len(context) - 1)

            context = self.denoise_elements(
                context,
                targets,
                steps=steps,
                shift=shift,
                guidance=guidance,
                uncond_fn=uncond_fn,
                generator=generator,
            )
        return context

    @torch.no_grad()
    def reconstruct(
        self,
        context: SpatialContext,
        *,
        steps: int = 32,
        shift: float = 1.0,
        generator: torch.Generator | None = None,
    ) -> tuple[SpatialContext, Tensor]:
        """Predict depth for every observed image and return a world pointmap.

        This is the 3D-reconstruction mode: the images are given (clean), only
        the depth elements are noise.  Because depth is expressed in the same
        spatial context as the images, unprojecting it yields a *fused* point
        cloud across all views with no separate alignment step.
        """
        image_indices = context.indices_of(IMAGE)
        if not image_indices:
            raise ValueError("reconstruction needs at least one image element")

        work = context
        depth_indices = []
        for idx in image_indices:
            cam = work[idx].cameras
            placeholder = torch.zeros(
                context.batch_size, 1, self.config.image_size, self.config.image_size, device=context.device
            )
            work = work.append(Element(DEPTH, placeholder, cam))
            depth_indices.append(len(work) - 1)

        work = self.denoise_elements(work, depth_indices, steps=steps, shift=shift, generator=generator)

        points = []
        for idx in depth_indices:
            el = work[idx]
            metric = decode_depth(el.data[:, 0])
            points.append(unproject_depth(el.cameras, metric))
        return work, torch.stack(points, dim=1)
