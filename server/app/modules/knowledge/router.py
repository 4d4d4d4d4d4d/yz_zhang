from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, not_found
from app.core.locks import job_slot
from app.core.admin_roles import require_role
from app.modules.account.models import User

from . import service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
# KB-070~076 子类的运营面（待定区、阈值标定、撤回、合并、改名）
admin_router = APIRouter(prefix="/admin/knowledge", tags=["knowledge-admin"])
# KB-088 / AGT-080~083 经验工具的调用（产出草稿；Agent 侧动作，不是谁都能点的按钮）
tools_router = APIRouter(prefix="/agent/tools", tags=["experience-tools"])


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
def admin_overview(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
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
def admin_undecided(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
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
def admin_assign(card_id: int, body: AssignIn, admin: User = Depends(require_role("ops")),
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
                            admin: User = Depends(require_role("ops")),
                            db: Session = Depends(get_db, scope="function")):
    """KB-071 标注用的候选对（相似度均匀铺开），运营逐对判「是不是一回事」后交给标定。"""
    from . import clusters

    return clusters.candidate_pairs(db, category, n)


@admin_router.post("/thresholds/{category}/calibrate")
def admin_calibrate(category: str, body: CalibrateIn, admin: User = Depends(require_role("ops")),
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
def admin_retract(task_id: int, body: RetractIn, admin: User = Depends(require_role("ops")),
                  db: Session = Depends(get_db, scope="function")):
    """KB-076 风控事后标记的任务：从子类里撤回，受影响的子类重算。"""
    from . import clusters

    res = clusters.retract_task(db, task_id)
    _audit(db, admin, "kb_retract", "task", task_id, body.reason)
    return res


@admin_router.post("/clusters/{cluster_id}/merge")
def admin_merge(cluster_id: int, body: MergeIn, admin: User = Depends(require_role("ops")),
                db: Session = Depends(get_db, scope="function")):
    from . import clusters

    dst = clusters.merge(db, cluster_id, body.target_id)
    _audit(db, admin, "kb_merge", "knowledge_cluster", cluster_id, f"并入子类 {dst.id}")
    return clusters.view(db, dst)


@admin_router.patch("/clusters/{cluster_id}")
def admin_rename(cluster_id: int, body: RenameIn, admin: User = Depends(require_role("ops")),
                 db: Session = Depends(get_db, scope="function")):
    from . import clusters
    from .models import KnowledgeCluster

    row = db.get(KnowledgeCluster, cluster_id)
    if row is None:
        raise not_found("子类不存在")
    old, row.label = row.label, body.label.strip()
    _audit(db, admin, "kb_rename", "knowledge_cluster", cluster_id, f"「{old}」→「{row.label}」")
    return clusters.view(db, row)


# ====================================================================== KB-080~089 可复用单元
@router.get("/units")
def list_units(category: str | None = Query(default=None, max_length=50),
               kind: str | None = Query(default=None, pattern="^(price_hint|checklist|procedure|skill_tool)$"),
               cluster_id: int | None = Query(default=None, ge=1),
               q: str = Query(default="", max_length=100),
               db: Session = Depends(get_db, scope="function")):
    """KB-086 可复用单元检索。只列**可用**的（在用、且有复用授权）；每个都带适用与排除条件、验证状态。"""
    from . import units
    from .models import ReusableUnit

    query = db.query(ReusableUnit).filter(ReusableUnit.status == "active", ReusableUnit.reuse_license.is_(True))
    if kind:
        query = query.filter(ReusableUnit.kind == kind)
    if cluster_id:
        query = query.filter(ReusableUnit.cluster_id == cluster_id)
    rows = [u for u in query.order_by(ReusableUnit.id.desc()).limit(100).all()
            if (not category or (u.applicability or {}).get("category") == category)
            and (not q.strip() or q.strip() in u.title)]
    return [units.view(db, u) for u in rows[:50]]


@router.get("/units/{unit_id}")
def unit_detail(unit_id: int, db: Session = Depends(get_db, scope="function")):
    """KB-087 单元详情：内容、适用与排除条件、验证结果、样本量、贡献者（只列同意了的人）。

    待复核、已停用的单元也读得到（状态写在里面）：用过它的人要能回来看它现在怎样了。
    **没有复用授权的单元不对外**：读它的内容就是在复用它，训练授权替代不了（KB-086）。
    """
    from . import units
    from .models import ReusableUnit

    row = db.get(ReusableUnit, unit_id)
    if row is None or not row.reuse_license:
        raise not_found("单元不存在")
    return units.view(db, row, detail=True)


class DistillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern="^(price_hint|checklist|procedure|skill_tool)$")
    title: str = Field(default="", max_length=120)
    cities: list[str] = Field(default_factory=list, max_length=50)
    budget_min_cents: int | None = Field(default=None, ge=0)
    budget_max_cents: int | None = Field(default=None, ge=0)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    scope: str = Field(default="platform", pattern="^(private|project|platform)$")
    reuse_license: bool
    train_license: bool
    tool: str = Field(default="", max_length=40)
    steps: list[dict] | None = Field(default=None, max_length=30)


@admin_router.post("/clusters/{cluster_id}/units", status_code=201)
def admin_distill(cluster_id: int, body: DistillIn, admin: User = Depends(require_role("ops")),
                  db: Session = Depends(get_db, scope="function")):
    """KB-080 从子类蒸馏一个可复用单元（第一版由运营确认生成，不做自动蒸馏——95 号第 8 节）。"""
    from . import units

    u = units.distill(
        db, cluster_id, body.kind, body.title,
        {"cities": body.cities, "budget_min_cents": body.budget_min_cents,
         "budget_max_cents": body.budget_max_cents, "exclusions": body.exclusions},
        body.scope, body.reuse_license, body.train_license, admin.id, body.tool,
        {"steps": body.steps} if body.steps else None)
    _audit(db, admin, "kb_unit_create", "reusable_unit", u.id,
           f"{u.kind}「{u.title}」来自子类 {cluster_id}，{len(u.sample_ids)} 个已授权样本")
    return units.view(db, u, detail=True)


@admin_router.get("/units")
def admin_units(status: str = Query(default="needs_review", pattern="^(active|needs_review|retired)$"),
                admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """KB-084 待复核的单元（返工与失败过半、或贡献者撤回了授权）。"""
    from . import units
    from .models import ReusableUnit

    rows = db.query(ReusableUnit).filter(ReusableUnit.status == status).order_by(ReusableUnit.id).limit(200).all()
    return [units.view(db, u) for u in rows]


class UnitStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(pattern="^(active|retired)$")
    note: str = Field(min_length=4, max_length=300)


@admin_router.patch("/units/{unit_id}")
def admin_unit_status(unit_id: int, body: UnitStatusIn, admin: User = Depends(require_role("ops")),
                      db: Session = Depends(get_db, scope="function")):
    """复核后重新启用（**版本号 +1、验证从头算**：复核前的结果属于上一版）或停用。"""
    from . import units
    from .models import ReusableUnit

    u = db.get(ReusableUnit, unit_id)
    if u is None:
        raise not_found("单元不存在")
    if body.status == "active":
        if not u.sample_ids:
            raise bad_request("来源样本已全部撤回，不能重新启用", "unit_no_consented_source")
        u.version += 1
        u.validation = {"status": "unvalidated", "uses": 0, "closed": 0, "reworked": 0, "failed": 0}
    u.status = body.status
    _audit(db, admin, "kb_unit_status", "reusable_unit", unit_id, f"{body.status}：{body.note}")
    return units.view(db, u, detail=True)


class InvokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: int = Field(ge=1)


@tools_router.post("/{unit_id}/invoke")
def invoke_tool(unit_id: int, body: InvokeIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    """KB-088 调用一个 skill_tool。产出一律是**草稿**（AGT-083），留痕（AGT-082），不碰钱（AGT-081）。"""
    import time

    from app.core.errors import forbidden
    from app.modules.task.models import Task

    from . import tools, units
    from .models import ReusableUnit

    unit = db.get(ReusableUnit, unit_id)
    if unit is None or unit.kind != "skill_tool":
        raise not_found("没有这个经验工具")
    try:
        units.tool_ready(unit)
    except units.ToolBlocked as b:
        raise b.http
    task = db.get(Task, body.task_id)
    if task is None:
        raise not_found("任务不存在")
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden("只有这一单的双方能用经验工具处理它")
    try:
        units.tool_applies(unit, task)
    except units.ToolBlocked as b:
        raise b.http
    started = time.monotonic()
    out = tools.RUNNERS[unit.content["tool"]](unit, task)
    inv = units.record_use(db, unit, "agent_tool", user.id, task.id,
                           summary=f"《{task.title}》", output=out, draft=True,
                           cost_cents=unit.est_cost_cents,
                           duration_ms=int((time.monotonic() - started) * 1000))
    return {"invocation_id": inv.id, "draft": True, "label": out["label"], "text": out["text"],
            "exclusions": (unit.applicability or {}).get("exclusions", []),
            "contributors": len(inv.beneficiaries)}


def settings_max_cost() -> int:
    from app.core.config import settings

    return settings.KB_TOOL_MAX_COST_CENTS


@tools_router.post("/invocations/{invocation_id}/discard")
def discard_draft(invocation_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    """AGT-083 草稿一键丢弃（只有调用它的人能丢）。丢弃也是结果：留着记录，标为已丢弃。"""
    from app.core.errors import forbidden

    from .models import UnitInvocation

    inv = db.get(UnitInvocation, invocation_id)
    if inv is None:
        raise not_found("没有这条草稿")
    if inv.caller_id != user.id:
        raise forbidden("只有生成它的人能丢弃")
    inv.discarded = True
    return {"invocation_id": inv.id, "discarded": True}
