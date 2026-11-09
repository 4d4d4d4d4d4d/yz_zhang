"""语义相似候选（L1 层，REQ-OR-010）。

可插拔的向量化接口：协议参数里登记“模型 ID”，所有节点用同一模型、同一版本计算，结果可复算。
内置确定性基线 `char-ngram-hash-v1`：字符 1-gram + 2-gram，log(1+tf) 加权，sha256 符号哈希
投影到 1024 维并 L2 归一化，相似度为余弦。

实测（改写过的同题文案 vs 无关文本）：同题最低 0.284、无关最高 0.179，阈值取 0.23。
这只是基线：它抓的是“用词重合”，对完全换词的洗稿无能为力。生产环境应接入固定版本的
多语言 embedding 模型（登记为新的模型 ID），本接口与调用方无需改动。
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections.abc import Callable

DIM = 1024
BASELINE = "char-ngram-hash-v1"
SIMILAR = 0.23  # 同题/追随候选
NEAR_DUP = 0.7  # 近重复（搬运）：实测轻改 15% 的搬运 >= 0.763，同题改写 <= 0.482，随机 <= 0.144

Vector = tuple[tuple[int, float], ...]  # 稀疏表示：((维度, 值), ...)，按维度排序
_NON_WORD = re.compile(r"[\W_]+")


def _normalize(text: str) -> str:
    return _NON_WORD.sub("", unicodedata.normalize("NFKC", text).lower())


def embed_baseline(text: str) -> Vector:
    s = _normalize(text)
    tf: dict[str, int] = {}
    for n in (1, 2):
        for i in range(len(s) - n + 1):
            g = s[i : i + n]
            tf[g] = tf.get(g, 0) + 1
    v: dict[int, float] = {}
    for g in sorted(tf):
        h = int.from_bytes(hashlib.sha256(g.encode("utf-8")).digest()[:4], "big")
        v[h % DIM] = v.get(h % DIM, 0.0) + (1.0 if (h >> 31) & 1 else -1.0) * (
            1.0 + math.log(tf[g])
        )
    norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
    return tuple((i, round(x / norm, 8)) for i, x in sorted(v.items()) if x != 0.0)


MODELS: dict[str, Callable[[str], Vector]] = {BASELINE: embed_baseline}


def register_model(model_id: str, fn: Callable[[str], Vector]) -> None:
    if model_id in MODELS:
        raise ValueError("模型 ID 已存在；升级模型必须使用新的 ID")
    MODELS[model_id] = fn


def embed(text: str, model_id: str = BASELINE) -> Vector:
    return MODELS[model_id](text)


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    db = dict(b)
    return sum(x * db.get(i, 0.0) for i, x in a)
