"""KB-070~076 经验按子类生长，而不是按样本堆积（108 号 spec，设计见 94 号）。

用户 2026-10-10：「知识图谱体系不可能把每个样本都添加，需要类似聚类一样，
把额外信息或者经验加到具体某个子类里，或者如果没有新建子类」。

一条经验进来时三条判定，对应三种**不同的错**：

    sim ≥ τ_merge                → 并入（增量更新质心与计数，不重算全表）
    τ_near ≤ sim < τ_merge        → 待定区（运营判：可能该分裂，也可能该放宽——方向相反）
    sim < τ_near                  → 新建子类（且标明「单样本」）

三条硬规则：

- **阈值按大类标定、带模型名**（KB-071）：没有标定、或标定时的模型与当前模型不一致，
  **拒绝归并并报警**——宁可不归并，不要用错的阈值归并。
- **退化模式不生长图谱**（KB-071b）：缺省的词袋哈希不是语义模型，用它自动新建子类，
  得到的是一张按字面相似度长出来的图，而没有人会发现。退化时只并入运营建的子类，
  其余全部进待定区。
- **分歧不许被平均掉**（KB-072）：共识之外，偏离共识却成功闭环的做法单独列出。
"""
from __future__ import annotations

import statistics
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import utcnow
from app.vendors.embedding import cosine
from app.vendors.registry import get_provider

from .models import ClusterThreshold, KnowledgeCard, KnowledgeCluster
from .retrieval import card_text, embed_many

OUTCOMES = ("completed", "disputed", "cancelled")
FRESH_DAYS = 180

# 归并被拒的原因 -> 计数（暴露到 /metrics）。取值有界
HELD_REASONS = ("no_threshold", "model_mismatch")
_held: dict[str, int] = {}


def held_counts() -> dict[str, int]:
    return {r: _held.get(r, 0) for r in HELD_REASONS}


def _provider_state() -> tuple[str, bool]:
    p = get_provider("embedding")
    return getattr(p, "model", ""), bool(getattr(p, "semantic", False))


# ------------------------------------------------------------------ 质心
def _mean(vectors: list[list[float]]) -> list[float]:
    if not vectors:
        return []
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def _members(db: Session, cluster_id: int) -> list[KnowledgeCard]:
    return (db.query(KnowledgeCard)
            .filter(KnowledgeCard.cluster_id == cluster_id, KnowledgeCard.cluster_state == "assigned")
            .order_by(KnowledgeCard.id).all())


def _add(cluster: KnowledgeCluster, card: KnowledgeCard) -> None:
    """KB-070a 增量并入：质心是成员向量的均值，n → n+1 不重算全表。"""
    n = cluster.sample_count
    if n == 0 or not cluster.centroid:
        cluster.centroid = list(card.embedding)
    else:
        cluster.centroid = [(c * n + v) / (n + 1) for c, v in zip(cluster.centroid, card.embedding)]
    cluster.sample_count = n + 1
    counts = dict(cluster.outcome_counts or {})
    counts[card.outcome] = counts.get(card.outcome, 0) + 1
    cluster.outcome_counts = counts
    if cluster.last_sample_at is None or card.created_at > cluster.last_sample_at:
        cluster.last_sample_at = card.created_at
    card.cluster_id = cluster.id
    card.cluster_state = "assigned"
    card.cluster_hint = {}


def recompute(db: Session, cluster: KnowledgeCluster) -> None:
    """撤回或合并之后按成员**精确重算**（增量减法会累积浮点误差，这里不省）。"""
    db.flush()
    members = _members(db, cluster.id)
    cluster.centroid = _mean([m.embedding for m in members])
    cluster.sample_count = len(members)
    counts: dict[str, int] = {}
    for m in members:
        counts[m.outcome] = counts.get(m.outcome, 0) + 1
    cluster.outcome_counts = counts
    cluster.last_sample_at = max((m.created_at for m in members), default=None)
    if not members and cluster.status == "active":
        cluster.status = "retired"


# ------------------------------------------------------------------ 排除
def exclusion(db: Session, card: KnowledgeCard) -> str:
    """风控标记的任务不进聚类：一次刷单进了质心就一直在里面（94 号第 6 节）。"""
    from app.modules.account.models import User
    from app.modules.aml.models import SuspiciousActivity
    from app.modules.task.models import Task

    if not card.source_task_id:
        return ""
    flagged = (db.query(SuspiciousActivity.id)
               .filter(SuspiciousActivity.ref_type == "task",
                       SuspiciousActivity.ref_id == card.source_task_id,
                       SuspiciousActivity.status != "cleared").first())
    if flagged:
        return "风控标记的任务"
    task = db.get(Task, card.source_task_id)
    if task:
        for uid in (task.creator_id, task.executor_id):
            u = db.get(User, uid) if uid else None
            if u is not None and u.is_banned:
                return "当事人已被封禁"
    return ""


# ------------------------------------------------------------------ 归并
def _ensure_embeddings(db: Session, cards: list[KnowledgeCard], model: str) -> None:
    stale = [c for c in cards if not c.embedding or c.embedding_model != model]
    if stale:
        vectors, model_name, _ = embed_many(db, [card_text(c) for c in stale])
        for c, v in zip(stale, vectors):
            c.embedding, c.embedding_model = v, model_name


def _nearest(db: Session, card: KnowledgeCard, model: str, ops_only: bool):
    q = db.query(KnowledgeCluster).filter(
        KnowledgeCluster.category == card.category, KnowledgeCluster.status == "active",
        KnowledgeCluster.embedding_model == model)
    best, best_sim = None, -1.0
    for c in q.all():
        if ops_only and not c.created_by.startswith("ops:"):
            continue
        if not c.centroid:
            continue
        sim = cosine(card.embedding, c.centroid)
        if sim > best_sim:
            best, best_sim = c, sim
    return best, best_sim


def process(db: Session, limit: int = 200) -> dict:
    """归并 job（串行，单实例锁由路由加）。处理 pending 与 held（标定好之后要重试）。"""
    model, semantic = _provider_state()
    cards = (db.query(KnowledgeCard)
             .filter(KnowledgeCard.cluster_state.in_(("pending", "held")))
             .order_by(KnowledgeCard.id).limit(limit).all())
    report = {"assigned": 0, "created": 0, "undecided": 0, "held": 0, "excluded": 0,
              "model": model, "semantic": semantic}
    if not cards:
        return report
    _ensure_embeddings(db, cards, model)
    thresholds = {t.category: t for t in db.query(ClusterThreshold).all()}

    for card in cards:
        why = exclusion(db, card)
        if why:
            card.cluster_state, card.cluster_hint = "excluded", {"reason": why}
            report["excluded"] += 1
            continue
        thr = thresholds.get(card.category)
        if thr is None or thr.embedding_model != model:
            reason = "no_threshold" if thr is None else "model_mismatch"
            _held[reason] = _held.get(reason, 0) + 1
            card.cluster_state = "held"
            card.cluster_hint = {"reason": reason, "note": (
                f"「{card.category}」还没有标定归并阈值" if thr is None else
                f"阈值是用 {thr.embedding_model} 标定的，当前模型是 {model}，须重标")}
            report["held"] += 1
            continue
        # 退化模式只并入运营建的子类（KB-071b）
        best, sim = _nearest(db, card, model, ops_only=not semantic)
        if best is not None and sim >= thr.tau_merge:
            _add(best, card)
            report["assigned"] += 1
        elif not semantic or (best is not None and sim >= thr.tau_near):
            card.cluster_state = "undecided"
            card.cluster_hint = {
                "nearest_id": best.id if best else None,
                "nearest_label": best.label if best else "",
                "similarity": round(sim, 4) if best else None,
                "why": ("当前 embedding 不是语义模型，不自动新建子类" if not semantic and (
                    best is None or sim < thr.tau_near) else "像又不够像：可能该分裂，也可能该放宽"),
            }
            report["undecided"] += 1
        else:
            cluster = KnowledgeCluster(category=card.category, label=card.title or card.category,
                                       embedding_model=model, created_by="auto",
                                       outcome_counts={}, centroid=[])
            db.add(cluster)
            db.flush()
            _add(cluster, card)
            report["created"] += 1
    db.flush()
    return report


# ------------------------------------------------------------------ 标定（KB-071）
def calibrate(db: Session, category: str, pairs: list[dict], admin_id: int) -> ClusterThreshold:
    """在人工标注的「是不是一回事」上扫 τ，取误并 + 误分最少的那个；并列时取高的（保守）。

    τ_near 取「被标成一回事的最低相似度」：低于它的从没被人认成一回事过 → 新建；
    [τ_near, τ_merge) 是标注里也有分歧的那一段 → 待定区。
    """
    same = [p for p in pairs if p.get("same")]
    diff = [p for p in pairs if not p.get("same")]
    if len(pairs) < 6 or len(same) < 2 or len(diff) < 2:
        raise bad_request("标注太少：至少 6 对，其中「是一回事」与「不是」各至少 2 对",
                          "calibration_too_few")
    model, _ = _provider_state()
    ids = {i for p in pairs for i in (p["a"], p["b"])}
    cards = {c.id: c for c in db.query(KnowledgeCard).filter(KnowledgeCard.id.in_(ids))}
    missing = ids - set(cards)
    if missing:
        raise not_found(f"这些样本不存在：{sorted(missing)}")
    if any(c.category != category for c in cards.values()):
        raise bad_request("标注对必须都在这个大类里：大类不同的样本永不并入同一子类",
                          "calibration_cross_category")
    _ensure_embeddings(db, list(cards.values()), model)
    sims = [(cosine(cards[p["a"]].embedding, cards[p["b"]].embedding), bool(p.get("same")))
            for p in pairs]
    candidates = sorted({round(s, 4) for s, _ in sims} | {1.0})
    best_tau, best_err = 1.0, len(sims) + 1
    for tau in candidates:
        err = sum(1 for s, is_same in sims if (s >= tau) != is_same)
        if err < best_err or (err == best_err and tau > best_tau):
            best_tau, best_err = tau, err
    tau_near = min(min(s for s, is_same in sims if is_same), best_tau)
    row = db.query(ClusterThreshold).filter(ClusterThreshold.category == category).first()
    if row is None:
        row = ClusterThreshold(category=category, calibrated_by=admin_id,
                               tau_merge=best_tau, tau_near=tau_near, embedding_model=model)
        db.add(row)
    row.tau_merge, row.tau_near, row.embedding_model = best_tau, round(tau_near, 4), model
    row.labeled_pairs, row.errors = len(pairs), best_err
    row.calibrated_by, row.calibrated_at = admin_id, utcnow()
    db.flush()
    return row


def candidate_pairs(db: Session, category: str, n: int = 12) -> list[dict]:
    """给运营标注用的候选对：从这个大类最近 60 个样本里挑，**均匀铺开相似度**——
    全是一眼就能判的对子标出来没有信息量，阈值就落在难判的那一段。"""
    model, _ = _provider_state()
    cards = (db.query(KnowledgeCard).filter(KnowledgeCard.category == category)
             .order_by(KnowledgeCard.id.desc()).limit(60).all())
    if len(cards) < 2:
        return []
    _ensure_embeddings(db, cards, model)
    pairs = sorted(((cosine(a.embedding, b.embedding), a, b)
                    for i, a in enumerate(cards) for b in cards[i + 1:]), key=lambda t: t[0])
    step = max(len(pairs) / n, 1)
    picked = [pairs[min(int(i * step), len(pairs) - 1)] for i in range(min(n, len(pairs)))]

    def brief(c):
        return {"card_id": c.id, "city": c.city, "title": c.title, "outcome": c.outcome,
                "price_actual_cents": c.price_actual_cents, "duration_days": c.duration_days}

    return [{"a": brief(a), "b": brief(b), "similarity": round(sim, 4)} for sim, a, b in picked]


# ------------------------------------------------------------------ 运营动作
def assign_by_ops(db: Session, card_id: int, admin_id: int, cluster_id: int | None,
                  new_label: str) -> KnowledgeCluster:
    """待定区的样本由运营判：并进某个子类，或新建一个（运营建的子类，退化模式下也可并入）。"""
    card = db.get(KnowledgeCard, card_id)
    if card is None:
        raise not_found("样本不存在")
    if card.cluster_state not in ("undecided", "held", "pending"):
        raise conflict("这条样本不在待定区", "card_not_undecided")
    model, _ = _provider_state()
    _ensure_embeddings(db, [card], model)
    if cluster_id is not None:
        cluster = db.get(KnowledgeCluster, cluster_id)
        if cluster is None or cluster.status != "active":
            raise not_found("子类不存在或已停用")
        if cluster.category != card.category:
            raise bad_request("大类不同的样本永不并入同一子类", "cluster_cross_category")
        if cluster.embedding_model != model:
            raise conflict("这个子类的质心是旧模型算的，先重算再并入", "cluster_model_mismatch")
    else:
        if not new_label.strip():
            raise bad_request("新建子类要有名字", "cluster_label_required")
        cluster = KnowledgeCluster(category=card.category, label=new_label.strip()[:120],
                                   embedding_model=model, created_by=f"ops:{admin_id}",
                                   outcome_counts={}, centroid=[])
        db.add(cluster)
        db.flush()
    _add(cluster, card)
    db.flush()
    return cluster


def retract_task(db: Session, task_id: int) -> dict:
    """KB-076 风控事后标记的任务：从子类里撤回，受影响的子类按剩余成员精确重算。"""
    cards = db.query(KnowledgeCard).filter(KnowledgeCard.source_task_id == task_id).all()
    if not cards:
        raise not_found("这个任务没有经验样本")
    touched = {c.cluster_id for c in cards if c.cluster_id}
    for c in cards:
        c.cluster_state, c.cluster_id = "retracted", None
        c.cluster_hint = {"reason": "运营撤回"}
    for cid in touched:
        recompute(db, db.get(KnowledgeCluster, cid))
    db.flush()
    return {"retracted": len(cards), "clusters_recomputed": sorted(touched)}


def merge(db: Session, source_id: int, target_id: int) -> KnowledgeCluster:
    """子类合并：成员搬过去，目标精确重算，源标成 merged 并指向目标（历史引用不悬空）。"""
    if source_id == target_id:
        raise bad_request("不能合并到自己", "cluster_merge_self")
    src, dst = db.get(KnowledgeCluster, source_id), db.get(KnowledgeCluster, target_id)
    if not src or not dst or src.status != "active" or dst.status != "active":
        raise not_found("子类不存在或已停用")
    if src.category != dst.category:
        raise bad_request("大类不同的子类不能合并", "cluster_cross_category")
    if src.embedding_model != dst.embedding_model:
        raise conflict("两个子类的质心不是同一个模型算的", "cluster_model_mismatch")
    for m in _members(db, src.id):
        m.cluster_id = dst.id
    recompute(db, dst)
    src.status, src.merged_into = "merged", dst.id
    src.sample_count, src.centroid, src.outcome_counts = 0, [], {}
    db.flush()
    return dst


# ------------------------------------------------------------------ 读（KB-073~075）
def _pct(values: list[int], q: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def view(db: Session, cluster: KnowledgeCluster, detail: bool = False) -> dict:
    members = _members(db, cluster.id) if cluster.status == "active" else []
    done = [m for m in members if m.outcome == "completed"]
    prices = [m.price_actual_cents for m in done if m.price_actual_cents > 0]
    days = [m.duration_days for m in done]
    total = len(members)
    counts = {o: (cluster.outcome_counts or {}).get(o, 0) for o in OUTCOMES}
    fresh_cut = utcnow() - timedelta(days=FRESH_DAYS)
    few = total < settings.KB_CLUSTER_MIN_SAMPLES
    out = {
        "id": cluster.id, "category": cluster.category, "label": cluster.label,
        "status": cluster.status, "merged_into": cluster.merged_into,
        "sample_count": total,
        # KB-073a 任何价格/工期结论都带样本量与时间范围
        "price_p50_cents": _pct(prices, 0.5), "price_p90_cents": _pct(prices, 0.9),
        "duration_p50_days": _pct(days, 0.5), "duration_p90_days": _pct(days, 0.9),
        "priced_samples": len(prices),
        "outcome_mix": counts,
        "first_sample_at": iso(min((m.created_at for m in members), default=None)),
        "last_sample_at": iso(cluster.last_sample_at),
        "recent_share": round(sum(1 for m in members if m.created_at >= fresh_cut) / total, 2) if total else 0.0,
        "few_samples": few,
        "note": f"样本过少（{total} 个），仅供参考" if few else "",
        "created_by": "ops" if cluster.created_by.startswith("ops:") else cluster.created_by,
    }
    if detail:
        out.update(_consensus(members))
        # KB-002 聚合可用 ≠ 个案可引用：个案证据要双方授权，平台尚未开放这项授权
        out["evidence"] = {"shown": [], "hidden": total,
                           "note": "个案需双方授权后才能展示；平台尚未开放个案引用授权，以上只给聚合结果"}
    return out


def _norm(t: str) -> str:
    return "".join(str(t).split()).lower()


def _consensus(members: list[KnowledgeCard]) -> dict:
    """KB-072 共识与分歧一起给，各带样本量。只出现在一个任务里的步骤文字不展示（k-匿名）。"""
    with_steps = [m for m in members if m.decomposition]
    if not with_steps:
        return {"consensus_steps": [], "dissent": [], "dissent_hidden": 0, "steps_basis": 0}
    seen: dict[str, dict] = {}
    for m in with_steps:
        keys = []
        for pos, st in enumerate(m.decomposition):
            k = _norm(st.get("title", ""))
            if not k or k in keys:
                continue
            keys.append(k)
            row = seen.setdefault(k, {"title": st.get("title", ""), "tasks": set(), "pos": []})
            row["tasks"].add(m.source_task_id or m.id)
            row["pos"].append(pos)
    n = len(with_steps)
    consensus_keys = [k for k, r in seen.items() if len(r["tasks"]) >= 2 and len(r["tasks"]) * 2 >= n]
    consensus_keys.sort(key=lambda k: statistics.mean(seen[k]["pos"]))
    cset = set(consensus_keys)
    variants: dict[frozenset, int] = {}
    for m in with_steps:
        if m.outcome != "completed":
            continue
        keys = frozenset(_norm(st.get("title", "")) for st in m.decomposition if st.get("title"))
        union = keys | cset
        jac = len(keys & cset) / len(union) if union else 1.0
        if jac < 0.5:
            variants[keys] = variants.get(keys, 0) + 1
    dissent, hidden = [], 0
    for keys, cnt in sorted(variants.items(), key=lambda kv: -kv[1]):
        if cnt < 2:
            hidden += cnt
            continue
        dissent.append({"steps": [seen[k]["title"] for k in keys if k in seen and len(seen[k]["tasks"]) >= 2],
                        "count": cnt})
    return {
        "consensus_steps": [{"title": seen[k]["title"], "count": len(seen[k]["tasks"])} for k in consensus_keys],
        "dissent": dissent,
        # 只出现过一次的不同做法：不展示文字（避免暴露个案），但数出来——分歧没有被抹掉
        "dissent_hidden": hidden,
        "steps_basis": n,
    }


def search(db: Session, category: str | None, q: str, limit: int = 20) -> dict:
    query = db.query(KnowledgeCluster).filter(KnowledgeCluster.status == "active")
    if category:
        query = query.filter(KnowledgeCluster.category == category)
    rows = query.all()
    model, semantic = _provider_state()
    if q.strip():
        vectors, _, _ = embed_many(db, [q])
        qv = vectors[0] if vectors else []

        def score(c):
            s = cosine(qv, c.centroid) if qv and c.centroid and c.embedding_model == model else 0.0
            return s + (1.0 if q.strip() in c.label else 0.0)

        rows = sorted(rows, key=score, reverse=True)
    else:
        rows = sorted(rows, key=lambda c: c.sample_count, reverse=True)
    return {"items": [view(db, c) for c in rows[:limit]], "semantic": semantic, "model": model}


def price_reference(db: Session, cluster_id: int) -> dict:
    """KB-075 按子类取分布。样本少于门槛的子类**不出价**，只说样本太少。"""
    cluster = db.get(KnowledgeCluster, cluster_id)
    if cluster is None or cluster.status != "active":
        raise not_found("子类不存在或已停用")
    v = view(db, cluster)
    if v["few_samples"] or not v["priced_samples"]:
        return {"sample_size": v["sample_count"], "cluster_id": cluster.id,
                "message": f"这个子类只有 {v['sample_count']} 个样本，不给参考价（至少 "
                           f"{settings.KB_CLUSTER_MIN_SAMPLES} 个）"}
    return {"sample_size": v["priced_samples"], "cluster_id": cluster.id,
            "p50_cents": v["price_p50_cents"], "p90_cents": v["price_p90_cents"],
            "first_sample_at": v["first_sample_at"], "last_sample_at": v["last_sample_at"]}
