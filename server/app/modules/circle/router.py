from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.im.models import Conversation

from .models import CIRCLE_KINDS, JOIN_POLICIES, Circle, CircleMember

router = APIRouter(prefix="/circles", tags=["circle"])


class CircleIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    description: str = ""
    kind: str = "interest"
    join_policy: str = "open"
    skill_tag: str = ""
    city: str = ""
    min_credit: int = Field(default=0, ge=0, le=200)


def _member(db: Session, circle_id: int, user_id: int) -> CircleMember | None:
    return (
        db.query(CircleMember)
        .filter(CircleMember.circle_id == circle_id, CircleMember.user_id == user_id)
        .first()
    )


def active_member(db: Session, circle_id: int, user_id: int) -> CircleMember | None:
    m = _member(db, circle_id, user_id)
    return m if m and m.status == "active" else None


def _dump(c: Circle, db: Session, viewer: User | None = None) -> dict:
    my = _member(db, c.id, viewer.id) if viewer else None
    return {
        "id": c.id, "name": c.name, "description": c.description, "kind": c.kind,
        "join_policy": c.join_policy, "owner_id": c.owner_id, "skill_tag": c.skill_tag,
        "city": c.city, "min_credit": c.min_credit, "member_count": c.member_count,
        "conversation_id": c.conversation_id,
        "my_status": my.status if my else None, "my_role": my.role if my else None,
    }


@router.post("", status_code=201)
def create_circle(body: CircleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.kind not in CIRCLE_KINDS:
        raise bad_request("非法圈层类型", "invalid_kind")
    if body.join_policy not in JOIN_POLICIES:
        raise bad_request("非法加入策略", "invalid_policy")
    if body.kind == "skill" and not body.skill_tag:
        raise bad_request("能力圈必须绑定技能标签", "skill_tag_required")
    if body.kind == "local" and not body.city:
        raise bad_request("地域圈必须绑定城市", "city_required")
    if db.query(Circle).filter(Circle.name == body.name).first():
        raise conflict("圈层名已存在", "name_taken")
    circle = Circle(owner_id=user.id, member_count=1, **body.model_dump())
    db.add(circle)
    db.flush()
    # CIR-006 圈层自带群聊
    conv = Conversation(kind="circle", participants=[user.id])
    db.add(conv)
    db.flush()
    circle.conversation_id = conv.id
    db.add_all([circle, CircleMember(circle_id=circle.id, user_id=user.id, role="owner")])
    db.flush()
    return _dump(circle, db, user)


@router.get("")
def discover(
    q: str | None = None,
    kind: str | None = None,
    recommended: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=20, le=100),
):
    """CIR-002 圈层发现：按兴趣/技能/城市推荐。"""
    query = db.query(Circle)
    if q:
        query = query.filter(Circle.name.contains(q) | Circle.description.contains(q))
    if kind:
        query = query.filter(Circle.kind == kind)
    rows = query.order_by(Circle.member_count.desc()).limit(200).all()
    if recommended:
        mine = {m.circle_id for m in db.query(CircleMember).filter(CircleMember.user_id == user.id)}
        tags = set(user.skills) | set(user.interests)

        def score(c: Circle) -> int:
            s = 0
            if c.skill_tag and c.skill_tag in tags:
                s += 2
            if c.city and c.city == user.city:
                s += 1
            return s

        rows = sorted([c for c in rows if c.id not in mine and score(c) > 0], key=score, reverse=True)
    return [_dump(c, db, user) for c in rows[:limit]]


@router.get("/{circle_id}")
def get_circle(circle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(Circle, circle_id)
    if not c:
        raise not_found("圈层不存在")
    return _dump(c, db, user)


@router.post("/{circle_id}/join")
def join(circle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CIR-003 加入：能力圈校验信用门槛；approval 制进入待审核。"""
    circle = db.get(Circle, circle_id)
    if not circle:
        raise not_found("圈层不存在")
    if _member(db, circle_id, user.id):
        raise conflict("已加入或待审核", "already_member")
    if circle.min_credit and user.credit_score < circle.min_credit:
        raise forbidden(f"该圈层要求信用分 ≥ {circle.min_credit}", "credit_too_low")
    status = "active" if circle.join_policy == "open" else "pending"
    db.add(CircleMember(circle_id=circle_id, user_id=user.id, status=status))
    if status == "active":
        _activate(db, circle, user.id)
    return {"status": status}


def _activate(db: Session, circle: Circle, user_id: int) -> None:
    circle.member_count += 1
    conv = db.get(Conversation, circle.conversation_id)
    if conv and user_id not in conv.participants:
        conv.participants = conv.participants + [user_id]
        db.add(conv)
    db.add(circle)


@router.post("/{circle_id}/members/{user_id}/approve")
def approve(
    circle_id: int, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """CIR-007 管理员审批加入申请。"""
    circle = db.get(Circle, circle_id)
    if not circle:
        raise not_found("圈层不存在")
    me = active_member(db, circle_id, user.id)
    if not me or me.role not in ("owner", "admin"):
        raise forbidden("需圈层管理员权限")
    m = _member(db, circle_id, user_id)
    if not m or m.status != "pending":
        raise not_found("无待审核申请")
    m.status = "active"
    db.add(m)
    _activate(db, circle, user_id)
    return {"status": "active"}


@router.post("/{circle_id}/members/{user_id}/remove")
def remove_member(
    circle_id: int, user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """CIR-007 移出成员。"""
    circle = db.get(Circle, circle_id)
    if not circle:
        raise not_found("圈层不存在")
    me = active_member(db, circle_id, user.id)
    if not me or me.role not in ("owner", "admin"):
        raise forbidden("需圈层管理员权限")
    m = _member(db, circle_id, user_id)
    if not m:
        raise not_found("成员不存在")
    if m.role == "owner":
        raise forbidden("不能移出圈主")
    was_active = m.status == "active"
    db.delete(m)
    if was_active:
        circle.member_count = max(1, circle.member_count - 1)
        conv = db.get(Conversation, circle.conversation_id)
        if conv and user_id in conv.participants:
            conv.participants = [p for p in conv.participants if p != user_id]
            db.add(conv)
        db.add(circle)
    return {"ok": True}


@router.get("/{circle_id}/members")
def members(circle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(CircleMember)
        .filter(CircleMember.circle_id == circle_id, CircleMember.status == "active")
        .all()
    )
    out = []
    for m in rows:
        u = db.get(User, m.user_id)
        out.append({"user_id": m.user_id, "nickname": u.nickname if u else "", "role": m.role,
                    "credit_score": u.credit_score if u else 0})
    return out


@router.get("/{circle_id}/feed")
def circle_feed(circle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CIR-004 圈层内容流（仅成员可见）。"""
    if not active_member(db, circle_id, user.id):
        raise forbidden("需加入圈层后查看", "not_circle_member")
    from app.modules.content.models import Content
    from app.modules.content.router import _dump as dump_content

    rows = (
        db.query(Content)
        .filter(Content.circle_id == circle_id, Content.status == "published")
        .order_by(Content.id.desc())
        .limit(50)
        .all()
    )
    return [dump_content(c, db, user) for c in rows]


@router.get("/{circle_id}/tasks")
def circle_tasks(circle_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CIR-005 圈层任务板（仅成员可见，圈内任务同样走合约托管）。"""
    if not active_member(db, circle_id, user.id):
        raise forbidden("需加入圈层后查看", "not_circle_member")
    from app.modules.task.models import Task
    from app.modules.task.router import dump_task

    rows = (
        db.query(Task)
        .filter(Task.circle_id == circle_id, Task.status == "published")
        .order_by(Task.id.desc())
        .limit(100)
        .all()
    )
    return [dump_task(t, user) for t in rows]
