"""文本指纹与近重复判定（L1 层）。

指纹由文本**确定性**计算，作者签名已覆盖文本，因此任何节点都可以复算指纹、
复核近重复判定，无需信任计算方。阈值来自实测：改字/加标点/调序/加开头 → 距离 0~10，
同题不同文/无关文本 → 距离 32 左右（64 位随机期望为 32）。

相关需求：REQ-OR-001, REQ-OR-008, REQ-OR-009
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from itertools import combinations

BITS = 64
SHINGLE = 3  # 字符 3-gram，对中文无需分词
NEAR_DUP_BITS = 12  # 汉明距离 <= 12 视为近重复
MIN_CHARS = 30  # 规范化后少于 30 字的文本太短，不做判定（避免误判）

_NON_WORD = re.compile(r"[\W_]+")


def normalize(text: str) -> str:
    """NFKC（全角转半角等）+ 小写 + 去掉所有标点与空白。"""
    return _NON_WORD.sub("", unicodedata.normalize("NFKC", text).lower())


def long_enough(text: str) -> bool:
    return len(normalize(text)) >= MIN_CHARS


def simhash(text: str) -> int:
    s = normalize(text)
    grams = [s[i : i + SHINGLE] for i in range(max(1, len(s) - SHINGLE + 1))]
    v = [0] * BITS
    for g in grams:
        h = int.from_bytes(hashlib.sha256(g.encode("utf-8")).digest()[:8], "big")
        for b in range(BITS):
            v[b] += 1 if (h >> b) & 1 else -1
    return sum(1 << b for b in range(BITS) if v[b] > 0)


def distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def is_near_duplicate(a: int, b: int) -> bool:
    return distance(a, b) <= NEAR_DUP_BITS


# ---------------- 媒体指纹（REQ-OR-008） ----------------
MEDIA_NEAR_BITS = 10  # 单帧 dHash 距离 <= 10 视为同一画面
MEDIA_MATCH_RATIO = 0.5  # 至少一半关键帧匹配才判为近重复


def _resize(gray: list[list[int]], w: int, h: int) -> list[list[float]]:
    """区域平均缩放（纯 Python，确定性）。"""
    src_h, src_w = len(gray), len(gray[0])
    out = []
    for y in range(h):
        y0, y1 = y * src_h // h, max(y * src_h // h + 1, (y + 1) * src_h // h)
        row = []
        for x in range(w):
            x0, x1 = x * src_w // w, max(x * src_w // w + 1, (x + 1) * src_w // w)
            cells = [gray[j][i] for j in range(y0, y1) for i in range(x0, x1)]
            row.append(sum(cells) / len(cells))
        out.append(row)
    return out


def dhash(gray: list[list[int]]) -> str:
    """差值哈希：缩放到 9x8 灰度，比较水平相邻像素，得到 64 位指纹（hex）。

    对重编码、缩放、轻度水印/调色鲁棒。帧由 L3 媒体服务解码后传入。
    """
    if not gray or not gray[0]:
        raise ValueError("空帧")
    small = _resize(gray, 9, 8)
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | (1 if small[y][x] < small[y][x + 1] else 0)
    return f"{bits:016x}"


def media_fingerprints(frames: list[list[list[int]]]) -> tuple[str, ...]:
    return tuple(dhash(f) for f in frames)


def media_near_duplicate(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    if not a or not b:
        return False
    hb = [int(x, 16) for x in b]
    matched = sum(1 for x in a if any(distance(int(x, 16), y) <= MEDIA_NEAR_BITS for y in hb))
    return matched / len(a) >= MEDIA_MATCH_RATIO


# ---------------- 指纹索引（REQ-OR-009） ----------------
class MultiIndex:
    """精确多索引哈希：64 位切成 4 段 x 16 位。

    抽屉原理：两个指纹距离 <= 12 时，至少有一段的差异 <= 3 位。查询时对每一段枚举
    差异 <= 3 位的所有 16 位变体（C(16,0..3) = 697 个）查桶，召回与线性扫描完全一致，
    而查询代价只与桶内元素数有关，与语料规模近似无关。
    """

    BANDS = 4
    BAND_BITS = 16

    def __init__(self) -> None:
        self._buckets: list[dict[int, list[str]]] = [{} for _ in range(self.BANDS)]
        self._fp: dict[str, int] = {}
        self._order: dict[str, int] = {}
        self._masks: dict[int, list[int]] = {}

    def _variants(self, radius: int) -> list[int]:
        if radius in self._masks:
            return self._masks[radius]
        out = [0]
        for r in range(1, radius + 1):
            for bits in combinations(range(self.BAND_BITS), r):
                m = 0
                for b in bits:
                    m |= 1 << b
                out.append(m)
        self._masks[radius] = out
        return out

    def _band(self, fp: int, i: int) -> int:
        return (fp >> (i * self.BAND_BITS)) & ((1 << self.BAND_BITS) - 1)

    def __len__(self) -> int:
        return len(self._fp)

    def add(self, key: str, fp: int) -> None:
        if key in self._fp:
            return
        self._fp[key] = fp
        self._order[key] = len(self._order)
        for i in range(self.BANDS):
            self._buckets[i].setdefault(self._band(fp, i), []).append(key)

    def query(self, fp: int, max_bits: int = NEAR_DUP_BITS) -> list[str]:
        """返回距离 <= max_bits 的键，按插入顺序（= 日志顺序）。召回精确（抽屉原理）。"""
        masks = self._variants(max_bits // self.BANDS)
        seen: set[str] = set()
        for i in range(self.BANDS):
            band = self._band(fp, i)
            bucket = self._buckets[i]
            for m in masks:
                for k in bucket.get(band ^ m, ()):
                    if k not in seen and distance(fp, self._fp[k]) <= max_bits:
                        seen.add(k)
        return sorted(seen, key=self._order.__getitem__)
