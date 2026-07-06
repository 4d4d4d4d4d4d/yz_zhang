from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db

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
