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
