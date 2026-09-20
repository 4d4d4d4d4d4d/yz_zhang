from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.task.service import machine_review

from .models import CONTENT_KINDS, VISIBILITIES, Comment, Content, Follow, Like
from app.core.timefmt import iso

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
    media_urls: list[str] = Field(default_factory=list, max_length=9)
    # CNT-003 草稿箱：默认发布，显式传 False 才存草稿
    publish: bool = True


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
        "media_urls": c.media_urls,
        "status": c.status,
        "source_task_id": c.source_task_id,
        "like_count": c.like_count,
        "comment_count": c.comment_count,
        "liked_by_me": liked,
        "created_at": iso(c.created_at),
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
    fields = body.model_dump()
    publish = fields.pop("publish")
    row = Content(author_id=user.id, status="published" if publish else "draft", **fields)
    db.add(row)
    db.flush()
    return _dump(row, db, user)


class ContentPatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    body: str | None = Field(default=None, max_length=20000)
    tags: list[str] | None = None
    media_urls: list[str] | None = Field(default=None, max_length=9)
    linked_category: str | None = None


@router.patch("/contents/{content_id}")
def edit_content(
    content_id: int, body: ContentPatchIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """CNT-003 编辑（草稿箱靠它反复存）。"""
    row = db.get(Content, content_id)
    if not row or row.status == "removed":
        raise not_found("内容不存在")
    if row.author_id != user.id:
        raise forbidden("仅作者可编辑")
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    # 改了文字就要重审：否则「先发一段干净的，再编辑成违规的」是条现成的绕过
    if "title" in patch or "body" in patch:
        hit = machine_review(f"{patch.get('title', row.title)} {patch.get('body', row.body)}")
        if hit:
            raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)
    return _dump(row, db, user)


@router.post("/contents/{content_id}/publish")
def publish_content(
    content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """草稿 → 发布。**发布时重跑机审**：草稿是随便改的，存草稿时审过不算数。"""
    row = db.get(Content, content_id)
    if not row or row.status == "removed":
        raise not_found("内容不存在")
    if row.author_id != user.id:
        raise forbidden("仅作者可发布")
    if row.status == "published":
        raise conflict("已经是发布状态", "already_published")
    if row.kind == "blog" and not row.title:
        raise bad_request("博客必须有标题", "title_required")
    hit = machine_review(f"{row.title} {row.body}")
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    row.status = "published"
    db.add(row)
    return _dump(row, db, user)


@router.get("/contents/mine")
def my_contents(
    status: str = Query(default="draft", pattern="^(draft|published)$"),
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """CNT-003 草稿箱。草稿**只有作者自己看得见**。"""
    rows = (
        db.query(Content)
        .filter(Content.author_id == user.id, Content.status == status)
        .order_by(Content.id.desc()).limit(limit).all()
    )
    return [_dump(c, db, user) for c in rows]


# ---------- KB-003 闭环任务一键生成经验帖 ----------
class ExperiencePostIn(BaseModel):
    body: str = Field(min_length=10, max_length=20000)
    title: str = Field(default="", max_length=120)


@router.post("/tasks/{task_id}/experience-post", status_code=201)
def create_experience_post(
    task_id: int, body: ExperiencePostIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """执行者为闭环任务写经验复盘，自动挂类目与案例来源（内容→能力→匹配打通）。"""
    from app.modules.task.models import Task

    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if user.id != task.executor_id:
        raise forbidden("仅任务执行者可发布经验帖")
    if task.status != "completed":
        raise conflict("任务闭环后才能发经验帖", "not_completed")
    hit = machine_review(body.title + " " + body.body)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    row = Content(
        author_id=user.id, kind="case",
        title=body.title or f"{task.title} · 完成复盘",
        body=body.body, tags=[task.category],
        linked_category=task.category, source_task_id=task.id,
    )
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
    # 作者能打开自己的草稿（否则草稿箱里点进去是 404，没法编辑）；
    # 别人一律看不见——草稿不是「还没推荐」，是「还没公开」
    if not c or (c.status != "published" and c.author_id != user.id):
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
             "body": r.body, "reply_to_id": r.reply_to_id, "created_at": iso(r.created_at)}
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
