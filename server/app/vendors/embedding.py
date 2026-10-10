"""KB-011 / KB-022 向量化与语义检索。

改造前 `knowledge/service.py` 的检索是关键词匹配，注释自己写着
「生产为向量检索 + LLM 生成，此处关键词匹配保证可测」。

这一批补的是**管线**：向量维度、供应商抽象、索引落库、余弦排序、
重建 job、RAG 端点。缺省实现仍是词袋哈希——

    ⚠️ **诚实说明**：词袋哈希不是语义模型，它捕捉的是词面重合，
    语义能力与关键词匹配基本相当。它的价值在于让整条管线是**真的**：
    维度、索引、相似度排序、重建流程都按真实形态跑。
    接真实模型只改 `PLATFORM_EMBEDDING_PROVIDER=http` 加一个端点，
    业务代码一行不动。

不把「没接真模型」藏起来：`/admin/vendors` 面板与 `model` 字段都会如实标明。
"""
import hashlib
import json
import math
import re
import urllib.request
from typing import Protocol

from .base import VendorError, VendorResult

_WORD = re.compile(r"[一-龥]|[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """中文按字、英文数字按词——检索侧与索引侧必须用同一套切分。"""
    return _WORD.findall((text or "").lower())


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int
    #: 真的是语义模型（而不是词面哈希）
    semantic: bool

    def embed(self, texts: list[str]) -> VendorResult:
        """返回 {"vectors": [[float, ...], ...]}。"""


class LocalBagOfWordsEmbedding:
    """缺省：确定性词袋哈希 + L2 归一化。无网络依赖，CI 可跑。

    `semantic = False` —— 这个字段存在的唯一目的就是不让人误以为已经接了
    语义模型。`/admin/vendors` 与 RAG 响应都会带上它。
    """

    name = "local"
    semantic = False

    def __init__(self, dim: int | None = None, model: str | None = None) -> None:
        from app.core.config import settings

        self.dim = dim or settings.EMBEDDING_DIM
        self.model = model or settings.EMBEDDING_MODEL

    def embed(self, texts: list[str]) -> VendorResult:
        vectors = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in tokenize(text):
                h = int(hashlib.blake2b(tok.encode(), digest_size=8).hexdigest(), 16)
                # 符号位取自另一段哈希，避免所有维度同号导致一切都相似
                vec[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec))
            vectors.append([v / norm for v in vec] if norm else vec)
        return VendorResult(ok=True, external_ref="", status="succeeded",
                            data={"vectors": vectors, "model": self.model,
                                  "semantic": False})


class HttpEmbedding:
    """任何 OpenAI 兼容的 `/v1/embeddings` 服务。

    形状是行业事实标准（OpenAI / 通义 / 智谱 / 本地 vLLM 都兼容），
    所以接哪一家只改 `PLATFORM_EMBEDDING_ENDPOINT`。
    """

    name = "http"
    semantic = True

    def __init__(self) -> None:
        from app.core.config import settings

        self.endpoint = settings.EMBEDDING_ENDPOINT
        self.token = settings.EMBEDDING_TOKEN
        self.model = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM

    def embed(self, texts: list[str]) -> VendorResult:
        if not self.endpoint:
            raise VendorError("embedding_not_configured",
                              "PLATFORM_EMBEDDING_PROVIDER=http 但没有配 ENDPOINT",
                              retryable=False)
        payload = json.dumps({"model": self.model, "input": texts}).encode()
        req = urllib.request.Request(self.endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                out = json.loads(resp.read())
        except Exception as exc:
            raise VendorError("embedding_upstream", f"向量服务不可用：{exc}",
                              retryable=True) from exc
        vectors = [d["embedding"] for d in out.get("data", [])]
        if len(vectors) != len(texts):
            raise VendorError("embedding_shape", "返回向量数与输入条数不符", retryable=False)
        return VendorResult(ok=True, external_ref=out.get("id", ""), status="succeeded",
                            data={"vectors": vectors, "model": self.model, "semantic": True})
