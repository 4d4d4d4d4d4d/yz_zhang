from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.locks import job_slot
from app.modules.account.models import User

from . import service

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/price-reference")
def price_reference(
    category: str = Query(min_length=1), city: str | None = None, db: Session = Depends(get_db)
):
    """KB-021 估价参考（分布 + 样本量）。"""
    return service.price_reference(db, category, city)


@router.get("/templates")
def templates(category: str, q: str = "", db: Session = Depends(get_db)):
    """KB-020 分解模板检索。"""
    tpl = service.find_template(db, category, q)
    return tpl or {"category": category, "items": [], "source": "none"}


@router.get("/category-demand")
def category_demand(db: Session = Depends(get_db)):
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
def cards(category: str | None = None, limit: int = 20, db: Session = Depends(get_db)):
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
    _: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """KB-022 统一检索入口。

    响应里的 `semantic` / `degraded` 是**有意暴露**的：缺省 embedding 是
    词袋哈希不是语义模型，没建索引时还会退化成词面命中。
    一个悄悄退化成关键词的「语义检索」比没有更糟——你不会去修它。
    """
    from .retrieval import search

    return search(db, q, kind=kind, top_k=top_k)


@router.post("/jobs/reindex")
def run_reindex(db: Session = Depends(get_db), _=Depends(require_job_auth),
                __=Depends(job_slot("kb_reindex"))):
    """KB-011 增量重建向量索引：只补没有向量或模型已换的行。"""
    from .retrieval import reindex

    return reindex(db)
