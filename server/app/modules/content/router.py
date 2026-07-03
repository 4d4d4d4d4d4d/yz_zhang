from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.task.service import machine_review

from .models import CONTENT_KINDS, VISIBILITIES, Comment, Content, Follow, Like

router = APIRouter(tags=["content"])


class ContentIn(BaseModel):
    kind: str = "post"
    title: str = Field(default="", max_length=120)
    body: str = Field(min_length=1, max_length=20000)
    tags: list[str] = []
    visibility: str = "public"
    circle_id: int | None = None
    linked_category: str = ""
    source_task_id: int | None = None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    reply_to_id: int | None = None


def _dump(c: Content, db: Session, viewer: User | None = None) -> dict:
    author = db.get(User, c.author_id)
    liked = False
    if viewer:
        liked = (
            db.query(Like).filter(Like.user_id == viewer.id, Like.content_id == c.id).first()
            is not None
        )
    return {
        "id": c.id,
        "author_id": c.author_id,
        "author_nickname": author.nickname if author else "",
        "kind": c.kind,
        "title": c.title,
        "body": c.body,
        "tags": c.tags,
        "visibility": c.visibility,
        "circle_id": c.circle_id,
        "linked_category": c.linked_category,
        "source_task_id": c.source_task_id,
        "like_count": c.like_count,
        "comment_count": c.comment_count,
        "liked_by_me": liked,
        "created_at": c.created_at.isoformat(),
    }


# ---------- 发布（CNT-001/003/006） ----------
@router.post("/contents", status_code=201)
def create_content(
    body: ContentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if body.kind not in CONTENT_KINDS:
        raise bad_request("非法内容类型", "invalid_kind")
    if body.visibility not in VISIBILITIES:
        raise bad_request("非法可见性", "invalid_visibility")
    if body.kind == "blog" and not body.title:
        raise bad_request("博客必须有标题", "title_required")
    # CNT-006 发布机审（复用任务违禁词，RISK-001 全场景覆盖）
    hit = machine_review(body.title + " " + body.body)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    if body.circle_id is not None:
        from app.modules.circle.models import CircleMember

        member = (
            db.query(CircleMember)
            .filter(
                CircleMember.circle_id == body.circle_id,
                CircleMember.user_id == user.id,
                CircleMember.status == "active",
            )
            .first()
        )
        if not member:
            raise forbidden("需先加入该圈层", "not_circle_member")
    row = Content(author_id=user.id, **body.model_dump())
    db.add(row)
    db.flush()
    return _dump(row, db, user)


# ---------- Feed（CNT-010/011 简化：关注流 + 最新流） ----------
@router.get("/feed")
def feed(
    scope: str = Query(default="latest", pattern="^(latest|following)$"),
    tag: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Content).filter(
        Content.status == "published",
        Content.visibility.in_(["public", "followers"]),
        Content.circle_id.is_(None),  # 圈层内容走圈层 feed（CIR-004）
    )
    if scope == "following":
        followee_ids = [
            f.followee_id for f in db.query(Follow).filter(Follow.follower_id == user.id).all()
        ]
        query = query.filter(Content.author_id.in_(followee_ids or [-1]))
    else:
        # 最新流只含 public
        query = query.filter(Content.visibility == "public")
    if kind:
        query = query.filter(Content.kind == kind)
    rows = query.order_by(Content.id.desc()).limit(500).all()
    if tag:
        rows = [c for c in rows if tag in c.tags]
    return [_dump(c, db, user) for c in rows[:limit]]


@router.get("/users/{user_id}/contents")
def user_contents(user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """主页作品列表（08.E 名片页数据源）。"""
    rows = (
        db.query(Content)
        .filter(Content.author_id == user_id, Content.status == "published")
        .order_by(Content.id.desc())
        .limit(50)
        .all()
    )
    visible = [c for c in rows if c.visibility == "public" or user_id == user.id]
    return [_dump(c, db, user) for c in visible]


@router.get("/contents/{content_id}")
def get_content(content_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    c = db.get(Content, content_id)
    if not c or c.status != "published":
        raise not_found("内容不存在")
    return _dump(c, db, user)


@router.delete("/contents/{content_id}")
def delete_content(content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(Content, content_id)
    if not c:
        raise not_found("内容不存在")
    if c.author_id != user.id and not user.is_admin:
        raise forbidden()
    c.status = "removed"
    db.add(c)
    return {"ok": True}


# ---------- 互动（CNT-020） ----------
@router.post("/contents/{content_id}/like")
def like(content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(Content, content_id)
    if not c or c.status != "published":
        raise not_found("内容不存在")
    existing = db.query(Like).filter(Like.user_id == user.id, Like.content_id == content_id).first()
    if existing:
        db.delete(existing)
        c.like_count = max(0, c.like_count - 1)
        db.add(c)
        return {"liked": False, "like_count": c.like_count}
    db.add(Like(user_id=user.id, content_id=content_id))
    c.like_count += 1
    db.add(c)
    return {"liked": True, "like_count": c.like_count}


@router.post("/contents/{content_id}/comments", status_code=201)
def comment(
    content_id: int, body: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    c = db.get(Content, content_id)
    if not c or c.status != "published":
        raise not_found("内容不存在")
    hit = machine_review(body.body)
    if hit:
        raise bad_request(f"评论含违禁信息（{hit}）", "content_rejected")
    row = Comment(content_id=content_id, author_id=user.id, body=body.body, reply_to_id=body.reply_to_id)
    c.comment_count += 1
    db.add_all([row, c])
    db.flush()
    return {"id": row.id}


@router.get("/contents/{content_id}/comments")
def list_comments(content_id: int, db: Session = Depends(get_db)):
    rows = db.query(Comment).filter(Comment.content_id == content_id).order_by(Comment.id).all()
    out = []
    for r in rows:
        author = db.get(User, r.author_id)
        out.append(
            {"id": r.id, "author_id": r.author_id, "author_nickname": author.nickname if author else "",
             "body": r.body, "reply_to_id": r.reply_to_id, "created_at": r.created_at.isoformat()}
        )
    return out


# ---------- 关注（CNT-021） ----------
@router.post("/users/{user_id}/follow")
def follow(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user_id == user.id:
        raise bad_request("不能关注自己", "self_follow")
    if not db.get(User, user_id):
        raise not_found("用户不存在")
    existing = (
        db.query(Follow).filter(Follow.follower_id == user.id, Follow.followee_id == user_id).first()
    )
    if existing:
        db.delete(existing)
        return {"following": False}
    db.add(Follow(follower_id=user.id, followee_id=user_id))
    return {"following": True}


@router.get("/users/{user_id}/follow-stats")
def follow_stats(user_id: int, db: Session = Depends(get_db)):
    followers = db.query(Follow).filter(Follow.followee_id == user_id).count()
    following = db.query(Follow).filter(Follow.follower_id == user_id).count()
    return {"followers": followers, "following": following}
