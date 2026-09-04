"""A tiny word-level tokenizer for scene captions.

Atlas is an *omni* model: text sits in the same sequence as images and depth.
The reproduction does not need a large language vocabulary -- it needs text
that genuinely describes the scene being generated, so that conditioning on
it is measurable.  A fixed word vocabulary over the procedural scene grammar
gives exactly that, with no tokenizer artefacts to debug.
"""

from __future__ import annotations

import torch
from torch import Tensor

__all__ = ["WordTokenizer", "SCENE_VOCAB"]

PAD, BOS, EOS, UNK = "<pad>", "<bos>", "<eos>", "<unk>"

SCENE_VOCAB: tuple[str, ...] = (
    PAD, BOS, EOS, UNK,
    "a", "an", "the", "and", "with", "of", "on", "in", "scene", "room",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "sphere", "spheres", "cube", "cubes", "box", "boxes", "ball", "balls",
    "red", "green", "blue", "yellow", "purple", "orange", "cyan", "white",
    "grey", "pink", "brown", "black",
    "large", "small", "tall", "wide", "floor", "wall", "light", "dark",
    "bright", "empty", "cluttered", "above", "near", "behind", "front",
)


class WordTokenizer:
    """Whitespace tokenizer over a closed vocabulary."""

    def __init__(self, vocab: tuple[str, ...] = SCENE_VOCAB, max_len: int = 32):
        self.vocab = list(vocab)
        self.max_len = max_len
        self.stoi = {w: i for i, w in enumerate(self.vocab)}
        self.pad_id = self.stoi[PAD]
        self.bos_id = self.stoi[BOS]
        self.eos_id = self.stoi[EOS]
        self.unk_id = self.stoi[UNK]

    def __len__(self) -> int:
        return len(self.vocab)

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    def encode(self, text: str, max_len: int | None = None) -> Tensor:
        max_len = self.max_len if max_len is None else max_len
        words = text.lower().replace(",", " ").split()
        ids = [self.bos_id] + [self.stoi.get(w, self.unk_id) for w in words] + [self.eos_id]
        ids = ids[:max_len]
        ids += [self.pad_id] * (max_len - len(ids))
        return torch.tensor(ids, dtype=torch.long)

    def encode_batch(self, texts: list[str], max_len: int | None = None) -> Tensor:
        return torch.stack([self.encode(t, max_len) for t in texts])

    def decode(self, ids: Tensor) -> str:
        words = []
        for i in ids.tolist():
            token = self.vocab[i] if 0 <= i < len(self.vocab) else UNK
            if token == EOS:
                break
            if token in (PAD, BOS):
                continue
            words.append(token)
        return " ".join(words)

    def null_prompt(self, batch: int, max_len: int | None = None, device=None) -> Tensor:
        """The empty caption used as the unconditional branch for guidance."""
        max_len = self.max_len if max_len is None else max_len
        ids = torch.full((batch, max_len), self.pad_id, dtype=torch.long, device=device)
        ids[:, 0] = self.bos_id
        ids[:, 1] = self.eos_id
        return ids
