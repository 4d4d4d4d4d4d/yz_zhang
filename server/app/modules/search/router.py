"""SRCH-001 统一搜索：任务/用户/内容/圈层一次查询分组返回。

MVP 用 SQL LIKE；规模化替换为 ES/OpenSearch，接口不变（12.C）。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.account.models import User
from app.modules.circle.models import Circle
from app.modules.content.models import Content
from app.modules.task.models import Task

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
def unified_search(
    q: str = Query(min_length=1, max_length=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=5, le=20),
):
    from app.modules.analytics.service import log_search

    log_search(db, q)  # SRCH-003 记录搜索词供热词/联想
    tasks = (
        db.query(Task)
        .filter(
            Task.status == "published", Task.visibility == "public",
            Task.title.contains(q) | Task.description.contains(q),
        )
        .order_by(Task.id.desc())
        .limit(limit)
        .all()
    )
    users = (
        db.query(User)
        .filter(User.nickname.contains(q), User.is_banned.is_(False))
        .limit(limit)
        .all()
    )
    contents = (
        db.query(Content)
        .filter(
            Content.status == "published", Content.visibility == "public",
            Content.circle_id.is_(None),
            Content.title.contains(q) | Content.body.contains(q),
        )
        .order_by(Content.id.desc())
        .limit(limit)
        .all()
    )
    circles = (
        db.query(Circle)
        .filter(Circle.name.contains(q) | Circle.description.contains(q))
        .order_by(Circle.member_count.desc())
        .limit(limit)
        .all()
    )
    return {
        "tasks": [
            {"id": t.id, "title": t.title, "category": t.category,
             "budget_cents": t.budget_cents, "city": t.city}
            for t in tasks
        ],
        "users": [
            {"id": u.id, "nickname": u.nickname, "skills": u.skills,
             "credit_score": u.credit_score, "rating_avg": u.rating_avg}
            for u in users
        ],
        "contents": [
            {"id": c.id, "kind": c.kind, "title": c.title,
             "body": c.body[:100], "author_id": c.author_id}
            for c in contents
        ],
        "circles": [
            {"id": c.id, "name": c.name, "kind": c.kind, "member_count": c.member_count}
            for c in circles
        ],
    }
