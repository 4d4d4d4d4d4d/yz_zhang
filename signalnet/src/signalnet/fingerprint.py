"""文本指纹与近重复判定（L1 层）。

指纹由文本**确定性**计算，作者签名已覆盖文本，因此任何节点都可以复算指纹、
复核近重复判定，无需信任计算方。阈值来自实测：改字/加标点/调序/加开头 → 距离 0~10，
同题不同文/无关文本 → 距离 32 左右（64 位随机期望为 32）。

相关需求：REQ-OR-001
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

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
