"""KB-011/022 向量索引与 RAG 检索。

改造前检索是关键词匹配，注释自己写着「生产为向量检索」。这里把整条管线
做真：向量化 → 落库 → 余弦排序 → 增量重建 → 统一 RAG 端点。

**缺省 embedding 是词袋哈希，不是语义模型**（`semantic=False`）。
所以本模块对外返回的每一个结果都带上 `semantic` 标志——
不让调用方（和读文档的人）误以为已经接了语义检索。
"""
from sqlalchemy.orm import Session

from app.vendors.embedding import cosine
from app.vendors.registry import get_provider

from .models import FaqEntry, KnowledgeCard

# 参与向量化的文本：卡片用类目+城市+标题，FAQ 用问题+答案+关键词
def card_text(c: KnowledgeCard) -> str:
    return f"{c.category} {c.city} {c.title}"


def faq_text(f: FaqEntry) -> str:
    return f"{f.question} {f.answer} {' '.join(f.keywords or [])}"


def embed_many(db: Session, texts: list[str]) -> tuple[list[list[float]], str, bool]:
    """批量向量化。走 `vendor_base.call` 拿熔断与留痕。"""
    from app.vendors import base as vendor_base

    provider = get_provider("embedding")
    if not texts:
        return [], getattr(provider, "model", ""), getattr(provider, "semantic", False)
    result = vendor_base.call(
        db, "embedding", provider.name, "embed", {"count": len(texts)},
        lambda: provider.embed(texts),
    )
    return (result.data["vectors"], result.data.get("model", ""),
            bool(result.data.get("semantic")))


def reindex(db: Session, limit: int = 500) -> dict:
    """KB-011 增量重建：只补**没有向量**或**模型已换**的行。

    全表重跑在真实模型下是要花钱的，而且换模型时两种向量混在一起做余弦
    会得到一堆毫无意义的相似度——所以 `embedding_model` 必须一起存。
    """
    provider = get_provider("embedding")
    model = getattr(provider, "model", "")
    done = 0
    for Model, textfn in ((KnowledgeCard, card_text), (FaqEntry, faq_text)):
        rows = [
            r for r in db.query(Model).limit(limit).all()
            if not r.embedding or r.embedding_model != model
        ]
        if not rows:
            continue
        vectors, model_name, _ = embed_many(db, [textfn(r) for r in rows])
        for row, vec in zip(rows, vectors):
            row.embedding = vec
            row.embedding_model = model_name
            db.add(row)
        done += len(rows)
    return {"reindexed": done, "model": model}


def search(db: Session, query: str, kind: str = "card", top_k: int = 5) -> dict:
    """KB-022 统一检索：向量排序，**向量缺失时退化为关键词**并如实标注。

    退化不是隐藏起来的——`degraded=True` 会原样返回给调用方。
    一个悄悄退化成关键词的「语义检索」比没有更糟：你不会去修它。
    """
    Model, textfn = ((KnowledgeCard, card_text) if kind == "card"
                     else (FaqEntry, faq_text))
    rows = db.query(Model).all()
    if not rows:
        return {"results": [], "semantic": False, "degraded": False, "model": ""}

    vectors, model, semantic = embed_many(db, [query])
    qvec = vectors[0] if vectors else []
    indexed = [r for r in rows if r.embedding and r.embedding_model == model]

    if qvec and indexed:
        scored = sorted(((cosine(qvec, r.embedding), r) for r in indexed),
                        key=lambda t: t[0], reverse=True)[:top_k]
        degraded = False
    else:
        # 没建索引/模型刚换：退化为词面命中，并**明确标注**
        from app.vendors.embedding import tokenize

        q = set(tokenize(query))
        scored = sorted(
            ((len(q & set(tokenize(textfn(r)))) / (len(q) or 1), r) for r in rows),
            key=lambda t: t[0], reverse=True)[:top_k]
        degraded = True

    return {
        "results": [{"id": r.id, "score": round(s, 4), "text": textfn(r)}
                    for s, r in scored if s > 0],
        "semantic": semantic and not degraded,
        "degraded": degraded,
        "model": model,
    }
