from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, get_optional_user
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


class _ListCtx:
    """一页内容共用的查询结果：作者、我点过赞的、我关注的作者。

    CONC-066（V128）：`_dump` 原来每条内容各查两次（作者 + 是否点赞），
    一页 20 条就是 40 多次查询。CNT-024 要再加「我是否关注了作者」，
    照原样逐条查就是 60 多次——所以列表接口改成**一页三次**。
    单条接口（详情、发布后回显）仍逐条查，那里只有一条。
    """

    def __init__(self, db: Session, viewer: User | None, rows: list[Content]):
        author_ids = {c.author_id for c in rows}
        self.authors = {u.id: u for u in db.query(User).filter(User.id.in_(author_ids or [-1]))}
        self.liked: set[int] = set()
        self.followed: set[int] = set()
        if viewer:
            ids = [c.id for c in rows] or [-1]
            self.liked = {r.content_id for r in db.query(Like.content_id)
                          .filter(Like.user_id == viewer.id, Like.content_id.in_(ids))}
            self.followed = {r.followee_id for r in db.query(Follow.followee_id)
                             .filter(Follow.follower_id == viewer.id,
                                     Follow.followee_id.in_(author_ids or [-1]))}


def _dump(c: Content, db: Session, viewer: User | None = None, ctx: _ListCtx | None = None) -> dict:
    if ctx is not None:
        author = ctx.authors.get(c.author_id)
        liked = c.id in ctx.liked
        follows_author = c.author_id in ctx.followed
    else:
        author = db.get(User, c.author_id)
        liked = False
        follows_author = False
        if viewer:
            liked = (
                db.query(Like).filter(Like.user_id == viewer.id, Like.content_id == c.id).first()
                is not None
            )
            follows_author = _follow_row(db, viewer.id, c.author_id) is not None
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
        # CNT-024 内容流里的关注按钮此前**没有状态**：永远写着「关注」，
        # 已关注的人点了没有任何变化，也没法从流里取消关注。
        # 自己的内容为 None——「对自己」这个问题没有意义（与 follow-stats 同一约定）。
        "author_followed_by_viewer": (
            None if viewer is None or viewer.id == c.author_id else follows_author
        ),
        "created_at": iso(c.created_at),
    }


# ---------- 发布（CNT-001/003/006） ----------
def can_view(db: Session, viewer: User, c: Content | None) -> bool:
    """SEC-060f 谁看得见一件作品：**只有这一个判据**，按 id 读、按作者列、评论、点赞都用它。

    此前按 id 读只看「已发布」，不看可见性——设成仅自己可见的作品，任何登录用户按 id 就能读。
    """
    if c is None or c.status == "removed":
        return False
    if c.author_id == viewer.id:
        return True
    if c.status != "published":
        return False
    if c.visibility == "public":
        return True
    if c.visibility == "followers":
        return _follow_row(db, viewer.id, c.author_id) is not None
    if c.visibility == "circle" and c.circle_id is not None:
        from app.modules.circle.router import active_member

        return active_member(db, c.circle_id, viewer.id) is not None
    return False


def _visible_or_404(db: Session, viewer: User, content_id: int) -> Content:
    """看不见就是不存在：403 会告诉别人这个 id 上确实有东西。"""
    c = db.get(Content, content_id)
    if not can_view(db, viewer, c):
        raise not_found("内容不存在")
    return c


@router.post("/contents", status_code=201)
def create_content(
    body: ContentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    if body.kind not in CONTENT_KINDS:
        raise bad_request("非法内容类型", "invalid_kind")
    if body.visibility not in VISIBILITIES:
        raise bad_request("非法可见性", "invalid_visibility")
    if body.kind == "blog" and not body.title:
        raise bad_request("博客必须有标题", "title_required")
    # CNT-006 发布机审（复用任务违禁词，RISK-001 全场景覆盖）
    hit = machine_review(body.title + " " + body.body, db)
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
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
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
        hit = machine_review(f"{patch.get('title', row.title)} {patch.get('body', row.body)}", db)
        if hit:
            raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)
    return _dump(row, db, user)


@router.post("/contents/{content_id}/publish")
def publish_content(
    content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
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
    hit = machine_review(f"{row.title} {row.body}", db)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}）", "content_rejected")
    row.status = "published"
    db.add(row)
    return _dump(row, db, user)


@router.get("/contents/mine")
def my_contents(
    status: str = Query(default="draft", pattern="^(draft|published)$"),
    limit: int = Query(default=20, le=100),
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
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
    user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function"),
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
    hit = machine_review(body.title + " " + body.body, db)
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
    db: Session = Depends(get_db, scope="function"),
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
    page = rows[:limit]
    ctx = _ListCtx(db, user, page)
    return [_dump(c, db, user, ctx) for c in page]


@router.get("/users/{user_id}/contents")
def user_contents(user_id: int, db: Session = Depends(get_db, scope="function"), user: User = Depends(get_current_user)):
    """主页作品列表（08.E 名片页数据源）。"""
    rows = (
        db.query(Content)
        .filter(Content.author_id == user_id, Content.status == "published")
        .order_by(Content.id.desc())
        .limit(50)
        .all()
    )
    visible = [c for c in rows if can_view(db, user, c)]
    ctx = _ListCtx(db, user, visible)
    return [_dump(c, db, user, ctx) for c in visible]


@router.get("/contents/{content_id}")
def get_content(content_id: int, db: Session = Depends(get_db, scope="function"), user: User = Depends(get_current_user)):
    # 作者能打开自己的草稿（否则草稿箱里点进去是 404，没法编辑）；
    # 别人一律看不见——草稿不是「还没推荐」，是「还没公开」
    c = _visible_or_404(db, user, content_id)
    return _dump(c, db, user)


@router.delete("/contents/{content_id}")
def delete_content(content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
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
def like(content_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    c = _visible_or_404(db, user, content_id)
    if c.status != "published":
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
    content_id: int, body: CommentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")
):
    c = _visible_or_404(db, user, content_id)
    if c.status != "published":
        raise not_found("内容不存在")
    hit = machine_review(body.body, db)
    if hit:
        raise bad_request(f"评论含违禁信息（{hit}）", "content_rejected")
    row = Comment(content_id=content_id, author_id=user.id, body=body.body, reply_to_id=body.reply_to_id)
    c.comment_count += 1
    db.add_all([row, c])
    db.flush()
    return {"id": row.id}


@router.get("/contents/{content_id}/comments")
def list_comments(content_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db, scope="function")):
    """评论不是独立的公开资源：作品看不见，它下面的评论也看不见（SEC-060f）。

    此前这个接口不要登录、不看状态、不看可见性——草稿、已删除、仅自己可见的作品下面的评论，未登录也能读。
    """
    _visible_or_404(db, user, content_id)
    rows = db.query(Comment).filter(Comment.content_id == content_id).order_by(Comment.id).limit(500).all()
    authors = {u.id: u for u in db.query(User).filter(User.id.in_({r.author_id for r in rows} or {-1}))}
    out = []
    for r in rows:
        author = authors.get(r.author_id)
        out.append(
            {"id": r.id, "author_id": r.author_id, "author_nickname": author.nickname if author else "",
             "body": r.body, "reply_to_id": r.reply_to_id, "created_at": iso(r.created_at)}
        )
    return out


# ---------- 关注（CNT-021） ----------
def _follow_row(db: Session, follower_id: int, followee_id: int) -> Follow | None:
    return (
        db.query(Follow)
        .filter(Follow.follower_id == follower_id, Follow.followee_id == followee_id)
        .first()
    )


def _check_followee(db: Session, user_id: int, me: User) -> None:
    if user_id == me.id:
        raise bad_request("不能关注自己", "self_follow")
    if not db.get(User, user_id):
        raise not_found("用户不存在")


@router.put("/users/{user_id}/follow")
def follow(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """CNT-022 关注。**幂等**：已关注再调一次仍然是已关注。

    改造前这里是一个 `POST` **toggle**，两个毛病：

    1. **重复调用会撤销**。手机上双击一下、或者弱网下客户端自动重试，
       用户刚关注的人就被取消关注了——而他看到的是自己点了两次「关注」。
    2. **客户端没法知道当前状态**（当时没有任何读接口回答「我是否已关注」），
       于是按钮只能猜。猜错 + toggle = **想关注却取消了关注**。

    幂等之后，「关注」与「取消关注」是两个不同的动作，重试多少次结果一样。
    """
    _check_followee(db, user_id, user)
    if not _follow_row(db, user.id, user_id):
        db.add(Follow(follower_id=user.id, followee_id=user_id))
    return {"following": True}


@router.delete("/users/{user_id}/follow")
def unfollow(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """CNT-022 取消关注。同样幂等：没关注过也返回「未关注」，不报错。

    不存在的关注当作已经达到目标状态——对「取消」这个动作来说，
    「本来就没有」和「刚刚删掉」对用户是同一件事。
    """
    _check_followee(db, user_id, user)
    row = _follow_row(db, user.id, user_id)
    if row:
        db.delete(row)
    return {"following": False}


@router.get("/users/{user_id}/follow-stats")
def follow_stats(user_id: int, db: Session = Depends(get_db, scope="function"),
                 viewer: User | None = Depends(get_optional_user)):
    """CNT-022 关注计数 + **访问者自己的关注状态**。

    `viewer_following` 是这一批补的那个读接口：没有它，想在页面上画
    「关注 / 已关注」就只能猜。匿名访问时为 `None`——**不是 `False`**：
    「没登录所以不知道」与「登录了但没关注」是两件事，
    合成一个 `False` 会让界面对游客显示「关注」按钮，点下去才发现要先登录。

    键名特意叫 `viewer_following` 而不是 `following`：这个响应里已经有一个
    `following`，而它是**「这个人关注了多少人」的计数**。同名不同义是个陷阱——
    客户端读成「我已关注」时，计数非零就会永远显示「已关注」。
    """
    followers = db.query(Follow).filter(Follow.followee_id == user_id).count()
    following = db.query(Follow).filter(Follow.follower_id == user_id).count()
    viewer_following = (
        None if viewer is None or viewer.id == user_id
        else _follow_row(db, viewer.id, user_id) is not None
    )
    return {"followers": followers, "following": following,
            "viewer_following": viewer_following}


def _publicly_listed(query):
    """出现在**别人**的关注列表里的人：与空间、搜索同一条可见性规则。

    关注关系本身就是个人信息：「谁关注了谁」会暴露一个人的兴趣与社交圈。
    设了资料不公开的人，不该因为他关注了某个公开的人，就出现在那个人的
    粉丝列表里给所有人看。
    """
    return query.filter(
        User.is_deleted.is_(False), User.is_banned.is_(False),
        or_(User.privacy["profile_public"].as_boolean().is_(None),
            User.privacy["profile_public"].as_boolean().is_(True)),
    )


def _follow_list(db: Session, user_id: int, viewer: User | None, direction: str,
                 after: int, limit: int) -> dict:
    """CNT-023 关注 / 粉丝列表。

    谁能看：**本人**总能看自己的；别人只能看资料公开的人的列表。
    列表里出现谁：本人看自己的列表时看得到所有未注销的人；
    别人看到的只有资料公开、未封禁、未注销的人（见 `_publicly_listed`）。

    游标是关注关系的 id（降序，新关注在前），不是页码——列表在翻页时
    还在变化（有人刚关注），页码会让同一个人出现两次或被跳过。
    """
    owner = db.get(User, user_id)
    if not owner or owner.is_deleted:
        raise not_found("用户不存在")
    is_self = viewer is not None and viewer.id == user_id
    if not is_self and (owner.is_banned
                        or (owner.privacy or {}).get("profile_public") is False):
        # 与公开资料页同一判断：不公开的人，他的社交圈也不公开。
        # 专用错误码：通用的 `forbidden` 会被客户端换成「无权执行该操作」，
        # 看的人就不知道**为什么**看不了；也不复用 `profile_private`——
        # 那个码的补救是「去改**你自己**的隐私设置」，对访客是错的指引。
        raise forbidden("对方未公开资料，看不到关注列表", "follow_list_private")

    if direction == "followers":
        join_on, key = Follow.follower_id, Follow.followee_id
    else:
        join_on, key = Follow.followee_id, Follow.follower_id
    query = (db.query(Follow, User).join(User, User.id == join_on)
             .filter(key == user_id))
    if is_self:
        query = query.filter(User.is_deleted.is_(False))
    else:
        query = _publicly_listed(query)
    if after:
        query = query.filter(Follow.id < after)
    rows = query.order_by(Follow.id.desc()).limit(limit + 1).all()
    page, more = rows[:limit], len(rows) > limit

    # 访问者自己关注了列表里的谁——一次查完，不逐个查
    shown = [u.id for _, u in page]
    mine: set[int] = set()
    if viewer and shown:
        mine = {r.followee_id for r in db.query(Follow.followee_id)
                .filter(Follow.follower_id == viewer.id, Follow.followee_id.in_(shown))}
    return {
        "items": [{
            "user_id": u.id, "nickname": u.nickname,
            "followed_at": iso(f.created_at),
            "viewer_following": (None if viewer is None or viewer.id == u.id
                                 else u.id in mine),
        } for f, u in page],
        "next_cursor": page[-1][0].id if more and page else None,
    }


@router.get("/users/{user_id}/followers")
def followers_list(user_id: int, after: int = Query(default=0, ge=0),
                   limit: int = Query(default=20, ge=1, le=50),
                   db: Session = Depends(get_db, scope="function"),
                   viewer: User | None = Depends(get_optional_user)):
    """CNT-023 谁关注了他。"""
    return _follow_list(db, user_id, viewer, "followers", after, limit)


@router.get("/users/{user_id}/following")
def following_list(user_id: int, after: int = Query(default=0, ge=0),
                   limit: int = Query(default=20, ge=1, le=50),
                   db: Session = Depends(get_db, scope="function"),
                   viewer: User | None = Depends(get_optional_user)):
    """CNT-023 他关注了谁。"""
    return _follow_list(db, user_id, viewer, "following", after, limit)
