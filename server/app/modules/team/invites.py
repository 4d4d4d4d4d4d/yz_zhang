"""TEAM-066 团队邀请链接（147 号 spec）。

此前加人只能由所有者填对方的用户编号——对方得先把编号报过来，而编号藏在个人空间地址里。
现在所有者生成一条链接发出去，对方点开看到是哪个团队、谁邀请、加入后的额度，登录后自己确认加入。
"""
import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import bad_request, conflict, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from . import service
from .models import Team, TeamInvite, TeamMember

router = APIRouter(tags=["team"])
MAX_ACTIVE_LINKS = 20


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class InviteLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spend_limit_cents: int = Field(default=0, ge=0, le=100_000_000)
    max_uses: int = Field(default=1, ge=1, le=50)
    days: int = Field(default=7, ge=1, le=30)


def _dump(r: TeamInvite) -> dict:
    now = utcnow()
    state = ("revoked" if r.revoked_at else "used_up" if r.uses >= r.max_uses
             else "expired" if r.expires_at <= now else "active")
    return {"id": r.id, "spend_limit_cents": r.spend_limit_cents, "uses": r.uses, "max_uses": r.max_uses,
            "expires_at": iso(r.expires_at), "created_at": iso(r.created_at), "state": state}


@router.post("/teams/{team_id}/invite-links", status_code=201)
def create_link(team_id: int, body: InviteLinkIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    """令牌只在这个响应里出现一次；库里只存哈希。"""
    if not db.get(Team, team_id):
        raise not_found("团队不存在")
    service.require_role(db, team_id, user.id, "owner")
    active = [r for r in db.query(TeamInvite).filter(TeamInvite.team_id == team_id, TeamInvite.revoked_at.is_(None))
              if _dump(r)["state"] == "active"]
    if len(active) >= MAX_ACTIVE_LINKS:
        raise conflict(f"同时有效的邀请链接最多 {MAX_ACTIVE_LINKS} 条：先作废用不到的", "team_invite_limit")
    token = secrets.token_urlsafe(18)
    row = TeamInvite(team_id=team_id, token_hash=_hash(token), spend_limit_cents=body.spend_limit_cents,
                     max_uses=body.max_uses, created_by=user.id, expires_at=utcnow() + timedelta(days=body.days))
    db.add(row)
    db.flush()
    return {**_dump(row), "token": token, "path": f"/teams/join/{token}",
            "warning": "这是唯一一次显示完整链接：库里只存哈希。丢了就作废重发。"}


@router.get("/teams/{team_id}/invite-links")
def list_links(team_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    if not db.get(Team, team_id):
        raise not_found("团队不存在")
    service.require_role(db, team_id, user.id, "owner")
    rows = db.query(TeamInvite).filter(TeamInvite.team_id == team_id).order_by(TeamInvite.id.desc()).limit(100).all()
    return [_dump(r) for r in rows]


@router.post("/teams/{team_id}/invite-links/{link_id}/revoke")
def revoke_link(team_id: int, link_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    service.require_role(db, team_id, user.id, "owner")
    row = db.get(TeamInvite, link_id)
    if not row or row.team_id != team_id:
        raise not_found("邀请链接不存在")
    if row.revoked_at is None:
        row.revoked_at = utcnow()
    return _dump(row)


def _usable(db: Session, token: str) -> TeamInvite:
    row = db.query(TeamInvite).filter(TeamInvite.token_hash == _hash(token)).first()
    if row is None or _dump(row)["state"] != "active":
        raise not_found("这条邀请链接无效：可能已过期、已用完或被作废。请找团队所有者重新发一条", "team_invite_invalid")
    return row


@router.get("/team-invites/{token}")
def preview(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """点开链接先看清楚：哪个团队、谁邀请、加入后的月度额度。不给成员名单。"""
    row = _usable(db, token)
    team = db.get(Team, row.team_id)
    inviter = db.get(User, row.created_by)
    return {"team_id": row.team_id, "team_name": team.name if team else "", "inviter_nickname": inviter.nickname if inviter else "",
            "role": "member", "spend_limit_cents": row.spend_limit_cents, "expires_at": iso(row.expires_at),
            "already_member": service.member_of(db, row.team_id, user.id) is not None}


@router.post("/team-invites/{token}/accept")
def accept(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    row = _usable(db, token)
    if service.member_of(db, row.team_id, user.id):
        raise conflict("你已经是这个团队的成员了", "already_member")
    if user.is_agent or user.is_venture or user.is_team:
        raise bad_request("AI 助理、合作体与团队账号不能作为团队成员", "invalid_member")
    # 使用次数用条件更新占位：两个人同时点最后一个名额，只有一个能进
    taken = (db.query(TeamInvite).filter(TeamInvite.id == row.id, TeamInvite.uses < TeamInvite.max_uses,
                                          TeamInvite.revoked_at.is_(None))
             .update({"uses": TeamInvite.uses + 1}, synchronize_session=False))
    if taken != 1:
        raise not_found("这条邀请链接刚刚用完了。请找团队所有者重新发一条", "team_invite_invalid")
    db.add(TeamMember(team_id=row.team_id, user_id=user.id, role="member", spend_limit_cents=row.spend_limit_cents))
    db.flush()
    return {"team_id": row.team_id, "user_id": user.id, "role": "member", "spend_limit_cents": row.spend_limit_cents}
