"""IM-003/020/021/022 好友与群聊。"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User, utcnow

from .models import Conversation
from .models_social import Friendship
from app.core.timefmt import iso

router = APIRouter(tags=["social"])


def _pair(db: Session, a: int, b: int) -> Friendship | None:
    return (
        db.query(Friendship)
        .filter(or_((Friendship.requester_id == a) & (Friendship.addressee_id == b),
                    (Friendship.requester_id == b) & (Friendship.addressee_id == a)))
        .first()
    )


class FriendRequestIn(BaseModel):
    user_id: int
    remark: str = Field(default="", max_length=50)


@router.post("/friends/requests", status_code=201)
def send_friend_request(
    body: FriendRequestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """IM-020 加好友：**双向同意**。

    单向加好友等于给任何人开了一条无需对方许可的私聊通道，
    而这个平台上陌生人之间本来就有真金白银的往来。
    """
    from app.modules.account.service import is_blocked_between

    if body.user_id == user.id:
        raise bad_request("不能加自己为好友", "self_friend")
    target = db.get(User, body.user_id)
    if not target or target.is_deleted:
        raise not_found("用户不存在")
    # ACC-033 拉黑优先于加好友——否则拉黑就成了一个可以被绕过的摆设
    if is_blocked_between(db, user.id, body.user_id):
        raise forbidden("对方不可用", "blocked")

    existing = _pair(db, user.id, body.user_id)
    if existing:
        if existing.status == "accepted":
            raise conflict("已经是好友", "already_friends")
        if existing.status == "pending":
            # 对方先发过请求：这一次「再发一遍」实质是同意，直接成好友。
            # 否则两个人各发一次会互相等待，谁都点不到「接受」。
            if existing.addressee_id == user.id:
                existing.status = "accepted"
                existing.decided_at = utcnow()
                db.add(existing)
                return {"id": existing.id, "status": "accepted"}
            raise conflict("请求已发出，等待对方确认", "request_pending")
        existing.status = "pending"        # 之前被拒过，允许再试
        existing.requester_id, existing.addressee_id = user.id, body.user_id
        existing.decided_at = None
        db.add(existing)
        return {"id": existing.id, "status": "pending"}

    row = Friendship(requester_id=user.id, addressee_id=body.user_id,
                     requester_remark=body.remark)
    db.add(row)
    db.flush()
    from app.modules.notification.service import notify

    notify(db, body.user_id, "interaction", "收到好友申请",
           f"{user.nickname or '有人'} 想加你为好友，去「通讯录」处理。")
    return {"id": row.id, "status": "pending"}


@router.get("/friends/requests")
def list_friend_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Friendship).filter(
        Friendship.addressee_id == user.id, Friendship.status == "pending").all()
    return [{"id": r.id, "from_user_id": r.requester_id,
             "created_at": iso(r.created_at)} for r in rows]


@router.post("/friends/requests/{req_id}/decide")
def decide_friend_request(
    req_id: int, accept: bool = Query(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    row = db.get(Friendship, req_id)
    if not row:
        raise not_found("申请不存在")
    if row.addressee_id != user.id:
        raise forbidden("仅被申请方可处理")
    if row.status != "pending":
        raise conflict("该申请已处理", "request_closed")
    row.status = "accepted" if accept else "rejected"
    row.decided_at = utcnow()
    db.add(row)
    return {"id": row.id, "status": row.status}


@router.get("/friends")
def list_friends(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IM-021 通讯录。备注名是**各自看各自的**，按方向取。"""
    rows = db.query(Friendship).filter(
        Friendship.status == "accepted",
        or_(Friendship.requester_id == user.id, Friendship.addressee_id == user.id)).all()
    out = []
    for r in rows:
        other_id = r.addressee_id if r.requester_id == user.id else r.requester_id
        remark = r.requester_remark if r.requester_id == user.id else r.addressee_remark
        other = db.get(User, other_id)
        out.append({"user_id": other_id, "nickname": other.nickname if other else "",
                    "remark": remark, "credit_score": other.credit_score if other else 0})
    return out


class RemarkIn(BaseModel):
    remark: str = Field(max_length=50)


@router.patch("/friends/{user_id}")
def set_remark(
    user_id: int, body: RemarkIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    row = _pair(db, user.id, user_id)
    if not row or row.status != "accepted":
        raise not_found("不是好友")
    if row.requester_id == user.id:
        row.requester_remark = body.remark
    else:
        row.addressee_remark = body.remark
    db.add(row)
    return {"user_id": user_id, "remark": body.remark}


@router.delete("/friends/{user_id}")
def remove_friend(
    user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = _pair(db, user.id, user_id)
    if row:
        db.delete(row)
    return {"ok": True}


@router.get("/friends/worked-with")
def worked_with(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """IM-022 合作过的人：**查出来的，不是存出来的**。

    存一张「合作过」表就要在每次闭环、每次取消、每次注销时同步维护它，
    而漏一处就是一条永远错着的记录。这里直接查已结算合约的对手方——
    它不可能过时。
    """
    from app.modules.contract.models import SETTLED_STATUSES, Contract

    rows = (
        db.query(Contract)
        .filter(or_(Contract.requester_id == user.id, Contract.executor_id == user.id),
                Contract.status.in_(tuple(SETTLED_STATUSES)))
        .all()
    )
    seen: dict[int, int] = {}
    for c in rows:
        other = c.executor_id if c.requester_id == user.id else c.requester_id
        if other and other != user.id:
            seen[other] = seen.get(other, 0) + 1
    out = []
    for uid, times in sorted(seen.items(), key=lambda kv: -kv[1]):
        u = db.get(User, uid)
        out.append({"user_id": uid, "nickname": u.nickname if u else "",
                    "times": times, "credit_score": u.credit_score if u else 0})
    return out


# ---------- IM-003 群聊 ----------
class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    member_ids: list[int] = Field(default_factory=list)


def _group(db: Session, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv or conv.kind != "group":
        raise not_found("群不存在")
    return conv


@router.post("/conversations/groups", status_code=201)
def create_group(
    body: GroupIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    members = sorted({user.id, *body.member_ids})
    if len(members) > settings.GROUP_MEMBER_LIMIT:
        raise bad_request(f"群成员上限 {settings.GROUP_MEMBER_LIMIT} 人", "group_too_large")
    conv = Conversation(kind="group", participants=members, owner_id=user.id, name=body.name)
    db.add(conv)
    db.flush()
    return {"id": conv.id, "name": conv.name, "members": members}


class MembersIn(BaseModel):
    user_ids: list[int] = Field(min_length=1)


@router.post("/conversations/{conv_id}/members")
def invite_members(
    conv_id: int, body: MembersIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    conv = _group(db, conv_id)
    if user.id not in conv.participants:
        raise forbidden("仅群成员可邀请")
    members = sorted(set(conv.participants) | set(body.user_ids))
    if len(members) > settings.GROUP_MEMBER_LIMIT:
        raise bad_request(f"群成员上限 {settings.GROUP_MEMBER_LIMIT} 人", "group_too_large")
    conv.participants = members
    db.add(conv)
    return {"id": conv.id, "members": members}


@router.delete("/conversations/{conv_id}/members/{member_id}")
def remove_member(
    conv_id: int, member_id: int,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """移出成员：仅群主；群主不能把自己移出（否则群主位空悬）。"""
    conv = _group(db, conv_id)
    if conv.owner_id != user.id:
        raise forbidden("仅群主可移出成员")
    if member_id == conv.owner_id:
        raise bad_request("群主不能移出自己，请先转让或解散", "owner_cannot_leave")
    conv.participants = [p for p in conv.participants if p != member_id]
    db.add(conv)
    return {"id": conv.id, "members": conv.participants}


class GroupPatchIn(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    announcement: str | None = Field(default=None, max_length=500)
    muted: list[int] | None = None


@router.patch("/conversations/{conv_id}")
def update_group(
    conv_id: int, body: GroupPatchIn,
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    conv = _group(db, conv_id)
    if conv.owner_id != user.id:
        raise forbidden("仅群主可修改群设置")
    if body.name is not None:
        conv.name = body.name
    if body.announcement is not None:
        conv.announcement = body.announcement
    if body.muted is not None:
        # 群主禁言自己没有意义，且会把自己锁在群外
        conv.muted = [u for u in body.muted if u != conv.owner_id]
    db.add(conv)
    return {"id": conv.id, "name": conv.name, "announcement": conv.announcement,
            "muted": conv.muted}
