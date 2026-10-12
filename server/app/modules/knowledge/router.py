from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin, require_job_auth
from app.core.errors import bad_request, not_found
from app.core.locks import job_slot
from app.modules.account.models import User

from . import service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
# KB-070~076 子类的运营面（待定区、阈值标定、撤回、合并、改名）
admin_router = APIRouter(prefix="/admin/knowledge", tags=["knowledge-admin"])


@router.get("/price-reference")
def price_reference(
    category: str = Query(min_length=1), city: str | None = None,
    cluster_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db, scope="function"),
):
    """KB-021 估价参考（分布 + 样本量）。KB-075 给 `cluster_id` 就按子类取：
    样本少于门槛的子类不出价（单样本的「中位数」是那一个数字，不是统计量）。"""
    if cluster_id is not None:
        from . import clusters

        return clusters.price_reference(db, cluster_id)
    return service.price_reference(db, category, city)


# ---------- KB-073/074 子类：这一类活儿通常怎么做、通常多少钱 ----------
@router.get("/clusters")
def list_clusters(category: str | None = Query(default=None, max_length=50),
                  q: str = Query(default="", max_length=100),
                  limit: int = Query(default=20, ge=1, le=50),
                  db: Session = Depends(get_db, scope="function")):
    """子类检索。返回的每个价格/工期结论都带样本量与时间范围（KB-073a）。"""
    from . import clusters

    return clusters.search(db, category, q, limit)


@router.get("/clusters/{cluster_id}")
def cluster_detail(cluster_id: int, db: Session = Depends(get_db, scope="function")):
    """子类详情：分布、结果构成、共识流程与分歧（KB-072）。

    合并掉的子类仍然读得到（状态 merged、指向合并去向）：历史引用不能悬空。
    """
    from . import clusters
    from .models import KnowledgeCluster

    row = db.get(KnowledgeCluster, cluster_id)
    if row is None:
        raise not_found("子类不存在")
    return clusters.view(db, row, detail=True)


@router.get("/templates")
def templates(category: str, q: str = "", db: Session = Depends(get_db, scope="function")):
    """KB-020 分解模板检索。"""
    tpl = service.find_template(db, category, q)
    return tpl or {"category": category, "items": [], "source": "none"}


@router.get("/category-demand")
def category_demand(db: Session = Depends(get_db, scope="function")):
    """KB-024 类目供需看板：按类目聚合在招任务数、闭环数、成交额、执行者供给数。"""
    from sqlalchemy import func

    from app.modules.account.models import User
    from app.modules.task.models import Task

    from .models import KnowledgeCard

    published = dict(
        db.query(Task.category, func.count(Task.id))
        .filter(Task.status == "published", Task.visibility == "public")
        .group_by(Task.category)
        .all()
    )
    completed = dict(
        db.query(KnowledgeCard.category, func.count(KnowledgeCard.id))
        .filter(KnowledgeCard.outcome == "completed")
        .group_by(KnowledgeCard.category)
        .all()
    )
    gmv = dict(
        db.query(KnowledgeCard.category, func.coalesce(func.sum(KnowledgeCard.price_actual_cents), 0))
        .filter(KnowledgeCard.outcome == "completed")
        .group_by(KnowledgeCard.category)
        .all()
    )
    # 供给：拥有对应技能标签的实名执行者数（技能 = 类目名的简化匹配）
    supply: dict[str, int] = {}
    for u in db.query(User).filter(User.is_verified.is_(True)).all():
        for skill in u.skills or []:
            supply[skill] = supply.get(skill, 0) + 1

    categories = set(published) | set(completed) | set(supply)
    rows = []
    for cat in sorted(categories):
        demand = published.get(cat, 0)
        sup = supply.get(cat, 0)
        rows.append({
            "category": cat,
            "open_demand": demand,
            "completed": completed.get(cat, 0),
            "gmv_cents": int(gmv.get(cat, 0)),
            "supply": sup,
            # 供需比 > 1 表示需求过热（缺人），< 1 表示供给过剩
            "demand_supply_ratio": round(demand / sup, 2) if sup else None,
        })
    return rows


@router.get("/cards")
def cards(category: str | None = None, limit: int = 20, db: Session = Depends(get_db, scope="function")):
    """脱敏经验卡列表（KB-023 用户侧攻略数据源）。"""
    from .models import KnowledgeCard

    query = db.query(KnowledgeCard)
    if category:
        query = query.filter(KnowledgeCard.category == category)
    rows = query.order_by(KnowledgeCard.id.desc()).limit(min(limit, 100)).all()
    return [
        {"id": r.id, "category": r.category, "city": r.city, "title": r.title,
         "price_actual_cents": r.price_actual_cents, "duration_days": r.duration_days,
         "outcome": r.outcome, "has_decomposition": bool(r.decomposition)}
        for r in rows
    ]

# ---------- KB-011/022 语义检索与 RAG ----------
@router.get("/search")
def knowledge_search(
    q: str = Query(min_length=1, max_length=200),
    kind: str = Query("card", pattern="^(card|faq)$"),
    top_k: int = Query(5, ge=1, le=20),
    _: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
):
    """KB-022 统一检索入口。

    响应里的 `semantic` / `degraded` 是**有意暴露**的：缺省 embedding 是
    词袋哈希不是语义模型，没建索引时还会退化成词面命中。
    一个悄悄退化成关键词的「语义检索」比没有更糟——你不会去修它。
    """
    from .retrieval import search

    return search(db, q, kind=kind, top_k=top_k)


@router.post("/jobs/cluster")
def run_cluster(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                __=Depends(job_slot("kb_cluster"), scope="function")):
    """KB-070 把新经验归进子类。**串行**：两个请求同时给同一子类更新质心，
    正是 V112/V118 那类静默错误的温床（94 号第 8 节）。"""
    from . import clusters

    return clusters.process(db)


@router.post("/jobs/reindex")
def run_reindex(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                __=Depends(job_slot("kb_reindex"), scope="function")):
    """KB-011 增量重建向量索引：只补没有向量或模型已换的行。"""
    from .retrieval import reindex

    return reindex(db)


# ====================================================================== 运营面
class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cluster_id: int | None = Field(default=None, ge=1)
    new_label: str = Field(default="", max_length=120)


class PairIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int
    b: int
    same: bool


class CalibrateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pairs: list[PairIn] = Field(min_length=6, max_length=500)


class RetractIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=4, max_length=300)


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_id: int = Field(ge=1)


class RenameIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=120)


def _audit(db, admin, action, target_type, target_id, detail):
    from app.modules.admin.router import record_audit

    record_audit(db, admin.id, action, target_type, target_id, detail)


@admin_router.get("/overview")
def admin_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    """各状态的样本数、各大类的阈值（含标定时的模型）、当前模型、被拒的归并次数。"""
    from sqlalchemy import func

    from app.core.timefmt import iso

    from . import clusters
    from .models import ClusterThreshold, KnowledgeCard, KnowledgeCluster

    model, semantic = clusters._provider_state()
    states = dict(db.query(KnowledgeCard.cluster_state, func.count(KnowledgeCard.id))
                  .group_by(KnowledgeCard.cluster_state).all())
    return {
        "model": model, "semantic": semantic,
        "states": {k: states.get(k, 0) for k in
                   ("pending", "assigned", "undecided", "held", "excluded", "retracted")},
        "active_clusters": db.query(KnowledgeCluster).filter(KnowledgeCluster.status == "active").count(),
        "thresholds": [{
            "category": t.category, "tau_merge": t.tau_merge, "tau_near": t.tau_near,
            "embedding_model": t.embedding_model, "stale": t.embedding_model != model,
            "labeled_pairs": t.labeled_pairs, "errors": t.errors, "calibrated_at": iso(t.calibrated_at),
        } for t in db.query(ClusterThreshold).order_by(ClusterThreshold.category)],
        "held": clusters.held_counts(),
    }


@admin_router.get("/undecided")
def admin_undecided(admin: User = Depends(require_admin), db: Session = Depends(get_db, scope="function")):
    """待定区与被拒归并的样本：带最像的子类与相似度，运营据此判。"""
    from app.core.timefmt import iso

    from .models import KnowledgeCard

    rows = (db.query(KnowledgeCard)
            .filter(KnowledgeCard.cluster_state.in_(("undecided", "held")))
            .order_by(KnowledgeCard.id).limit(200).all())
    return [{"card_id": r.id, "category": r.category, "city": r.city, "title": r.title,
             "outcome": r.outcome, "state": r.cluster_state, "hint": r.cluster_hint or {},
             "created_at": iso(r.created_at)} for r in rows]


@admin_router.post("/cards/{card_id}/assign")
def admin_assign(card_id: int, body: AssignIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db, scope="function")):
    """把待定区的样本并进某个子类，或以它为第一个样本新建子类（二选一）。"""
    from . import clusters

    if (body.cluster_id is None) == (not body.new_label.strip()):
        raise bad_request("并进已有子类、或新建子类，二选一", "assign_choose_one")
    c = clusters.assign_by_ops(db, card_id, admin.id, body.cluster_id, body.new_label)
    _audit(db, admin, "kb_assign", "knowledge_card", card_id, f"并入子类 {c.id}「{c.label}」")
    return clusters.view(db, c)


@admin_router.get("/thresholds/{category}/pairs")
def admin_calibration_pairs(category: str, n: int = Query(default=12, ge=6, le=40),
                            admin: User = Depends(require_admin),
                            db: Session = Depends(get_db, scope="function")):
    """KB-071 标注用的候选对（相似度均匀铺开），运营逐对判「是不是一回事」后交给标定。"""
    from . import clusters

    return clusters.candidate_pairs(db, category, n)


@admin_router.post("/thresholds/{category}/calibrate")
def admin_calibrate(category: str, body: CalibrateIn, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db, scope="function")):
    """KB-071 用人工标注的「是不是一回事」标定这个大类的阈值（换模型后必须重标）。"""
    from app.core.timefmt import iso

    from . import clusters

    t = clusters.calibrate(db, category, [p.model_dump() for p in body.pairs], admin.id)
    _audit(db, admin, "kb_calibrate", "knowledge_threshold", t.id,
           f"{category}：τ_merge={t.tau_merge} τ_near={t.tau_near}（{t.labeled_pairs} 对，误判 {t.errors}）")
    return {"category": t.category, "tau_merge": t.tau_merge, "tau_near": t.tau_near,
            "embedding_model": t.embedding_model, "labeled_pairs": t.labeled_pairs,
            "errors": t.errors, "calibrated_at": iso(t.calibrated_at)}


@admin_router.post("/tasks/{task_id}/retract")
def admin_retract(task_id: int, body: RetractIn, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db, scope="function")):
    """KB-076 风控事后标记的任务：从子类里撤回，受影响的子类重算。"""
    from . import clusters

    res = clusters.retract_task(db, task_id)
    _audit(db, admin, "kb_retract", "task", task_id, body.reason)
    return res


@admin_router.post("/clusters/{cluster_id}/merge")
def admin_merge(cluster_id: int, body: MergeIn, admin: User = Depends(require_admin),
                db: Session = Depends(get_db, scope="function")):
    from . import clusters

    dst = clusters.merge(db, cluster_id, body.target_id)
    _audit(db, admin, "kb_merge", "knowledge_cluster", cluster_id, f"并入子类 {dst.id}")
    return clusters.view(db, dst)


@admin_router.patch("/clusters/{cluster_id}")
def admin_rename(cluster_id: int, body: RenameIn, admin: User = Depends(require_admin),
                 db: Session = Depends(get_db, scope="function")):
    from . import clusters
    from .models import KnowledgeCluster

    row = db.get(KnowledgeCluster, cluster_id)
    if row is None:
        raise not_found("子类不存在")
    old, row.label = row.label, body.label.strip()
    _audit(db, admin, "kb_rename", "knowledge_cluster", cluster_id, f"「{old}」→「{row.label}」")
    return clusters.view(db, row)
