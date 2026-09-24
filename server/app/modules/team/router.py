"""TEAM 团队账户端点（53 号 spec）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_verified
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.wallet import service as wallet

from . import service
from .models import ROLES, SpendRequest, Team, TeamMember
from app.core.timefmt import iso

router = APIRouter(prefix="/teams", tags=["team"])


class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)


class MemberIn(BaseModel):
    user_id: int
    role: str = Field(default="member", pattern="^(admin|member)$")
    spend_limit_cents: int = Field(default=0, ge=0)


class MemberPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|member)$")
    spend_limit_cents: int | None = Field(default=None, ge=0)


class SpendIn(BaseModel):
    amount_cents: int = Field(gt=0)
    purpose: str = Field(default="", max_length=200)
    task_id: int | None = None


class DecideIn(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=1000)


class BudgetIn(BaseModel):
    # 0 = 不设池。允许调低到已用量之下：那表示「这个月不许再花了」，
    # 是一个合法的意思表示，不该被拦。
    monthly_budget_cents: int = Field(ge=0)


class CompanyIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    tax_number: str = Field(min_length=6, max_length=40)
    license_images: list[str] = Field(default_factory=list)


def _dump(t: Team) -> dict:
    return {"id": t.user_id, "name": t.name, "owner_id": t.owner_id,
            "company_name": t.company_name, "tax_number": t.tax_number,
            "verify_status": t.verify_status, "verify_reason": t.verify_reason,
            "active": t.active}


def _get(db: Session, team_id: int) -> Team:
    t = db.get(Team, team_id)
    if not t:
        raise not_found("团队不存在")
    return t


@router.post("", status_code=201)
def create_team(body: TeamIn, user: User = Depends(require_verified),
                db: Session = Depends(get_db)):
    """建团队 = 建一行 User + 一行 Team。

    与 V73「agent 是 User」、V75「合作体是 User」同一条理由：
    钱包/托管/合约/纠纷/发任务全部以 user_id 为键。
    """
    team_user = User(
        phone=f"team:{body.name}:{user.id}", nickname=body.name,
        is_team=True, is_verified=True, is_adult=True,
        accepting_orders=False,     # 团队是发布方，不接单
    )
    db.add(team_user)
    db.flush()
    team = Team(user_id=team_user.id, name=body.name, owner_id=user.id)
    db.add(team)
    db.add(TeamMember(team_id=team_user.id, user_id=user.id, role="owner",
                      spend_limit_cents=0))
    db.flush()
    return _dump(team)


@router.get("/mine")
def my_teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TeamMember).filter(TeamMember.user_id == user.id,
                                       TeamMember.active.is_(True)).all()
    out = []
    for m in rows:
        t = db.get(Team, m.team_id)
        if t:
            out.append({**_dump(t), "my_role": m.role,
                        "my_spend_limit_cents": m.spend_limit_cents})
    return out


@router.get("/{team_id}")
def get_team(team_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    team = _get(db, team_id)
    me = service.require_member(db, team_id, user.id)
    acct = wallet.get_or_create(db, team_id)
    members = db.query(TeamMember).filter(TeamMember.team_id == team_id,
                                          TeamMember.active.is_(True)).all()
    return {
        **_dump(team),
        "balance_cents": acct.available_cents,
        "my_role": me.role, "my_spend_limit_cents": me.spend_limit_cents,
        "members": [{"user_id": m.user_id, "role": m.role,
                     "spend_limit_cents": m.spend_limit_cents} for m in members],
        # TEAM-030 客户端的「开票」按钮读这个，与服务端同一判断
        "invoice_block": service.can_invoice(team),
        # TEAM-052 预算池与本月用量：界面要能说清「还剩多少」，
        # 只显示「超额」的话，人不知道该改金额还是该改池子
        "monthly_budget_cents": team.monthly_budget_cents,
        "month_spent_cents": service.team_spent_this_month(db, team_id),
        "my_month_spent_cents": service.member_spent_this_month(db, team_id, user.id),
    }


# ------------------------------------------------------------------- 成员与权限
@router.post("/{team_id}/members", status_code=201)
def add_member(team_id: int, body: MemberIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    team = _get(db, team_id)
    service.require_role(db, team_id, user.id, "owner")
    if service.member_of(db, team_id, body.user_id):
        raise conflict("已是团队成员", "already_member")
    target = db.get(User, body.user_id)
    if not target:
        raise not_found("用户不存在")
    if target.is_agent or target.is_venture or target.is_team:
        raise bad_request("AI 助理、合作体与团队账号不能作为团队成员",
                          "invalid_member")
    db.add(TeamMember(team_id=team.user_id, user_id=body.user_id, role=body.role,
                      spend_limit_cents=body.spend_limit_cents))
    db.flush()
    return {"team_id": team_id, "user_id": body.user_id, "role": body.role}


@router.patch("/{team_id}/members/{member_user_id}")
def patch_member(team_id: int, member_user_id: int, body: MemberPatch,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """TEAM-010 **只有 owner 能改角色与额度。**

    admin 能批支出但不能给自己提额度——否则「审批」这道闸门自己就绕过去了。
    """
    _get(db, team_id)
    service.require_role(db, team_id, user.id, "owner")
    m = service.member_of(db, team_id, member_user_id)
    if not m:
        raise not_found("成员不存在")
    if m.role == "owner":
        raise bad_request("不能修改 owner 的角色或额度", "owner_immutable")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(m, field, value)
    db.add(m)
    return {"user_id": m.user_id, "role": m.role,
            "spend_limit_cents": m.spend_limit_cents}


@router.delete("/{team_id}/members/{member_user_id}")
def remove_member(team_id: int, member_user_id: int,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get(db, team_id)
    service.require_role(db, team_id, user.id, "owner")
    m = service.member_of(db, team_id, member_user_id)
    if not m:
        raise not_found("成员不存在")
    if m.role == "owner":
        raise bad_request("不能移出 owner", "owner_immutable")
    m.active = False
    db.add(m)
    return {"removed": member_user_id}


# ------------------------------------------------------------------- 支出与审批
@router.post("/{team_id}/spends", status_code=201)
def request_spend(team_id: int, body: SpendIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """发起一笔团队支出。额度内直接执行，超额转审批。"""
    team = _get(db, team_id)
    me = service.require_member(db, team_id, user.id)
    block = service.spend_block(db, team, me, body.amount_cents)
    req = service.create_spend_request(db, team, user, body.amount_cents,
                                       body.purpose, body.task_id)
    if not block:
        # 额度内：直接批准并执行，但**仍然留一条记录**——
        # 「谁花了公司多少钱」这件事不该因为在额度内就查不到
        req.status = "approved"
        req.decided_by = user.id
        req.decision_reason = "额度内自动批准"
        db.add(req)
        db.flush()
        result = service.execute_spend(db, req, user)
        return {**result, "needed_approval": False}
    # TEAM-060 只有真的进审批才通知——额度内自动批准的那条路没有人要做事
    service.notify_pending(db, team, req, user)
    return {"id": req.id, "status": req.status, "amount_cents": req.amount_cents,
            "needed_approval": True, "reason": block}


@router.get("/{team_id}/spends")
def list_spends(team_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    _get(db, team_id)
    me = service.require_member(db, team_id, user.id)
    q = db.query(SpendRequest).filter(SpendRequest.team_id == team_id)
    # member 只看自己的；owner/admin 看全部
    if me.role == "member":
        q = q.filter(SpendRequest.requester_id == user.id)
    rows = q.order_by(SpendRequest.id.desc()).limit(100).all()
    return [
        {"id": r.id, "requester_id": r.requester_id, "amount_cents": r.amount_cents,
         "purpose": r.purpose, "status": r.status, "task_id": r.task_id,
         "decided_by": r.decided_by, "decision_reason": r.decision_reason,
         "created_at": iso(r.created_at),
         # 客户端的「审批」按钮读这个，与服务端同一判断（TEAM-021）
         "can_decide": (r.status == "pending" and me.role in ("owner", "admin")
                        and r.requester_id != user.id)}
        for r in rows
    ]


@router.post("/{team_id}/spends/{request_id}/decide")
def decide(team_id: int, request_id: int, body: DecideIn,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get(db, team_id)
    req = db.get(SpendRequest, request_id)
    if not req or req.team_id != team_id:
        raise not_found("支出申请不存在")
    req = service.decide_spend(db, req, user, body.approve, body.reason)
    # TEAM-061 理由要当场回给调用方：平台强制写了它，就别再逼界面
    # 重新拉一次列表才能显示
    return {"id": req.id, "status": req.status, "decision_reason": req.decision_reason}


@router.post("/{team_id}/spends/{request_id}/execute")
def execute(team_id: int, request_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    _get(db, team_id)
    req = db.get(SpendRequest, request_id)
    if not req or req.team_id != team_id:
        raise not_found("支出申请不存在")
    return service.execute_spend(db, req, user)


@router.post("/{team_id}/budget")
def set_budget(team_id: int, body: BudgetIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """TEAM-052 设团队月度预算池。**只有 owner 能改**：

    池子是「这个月团队总共花多少」的总量声明，而 admin 是被授予权限的人。
    让 admin 自己改池子，等于让他绕过自己受的约束。
    """
    team = _get(db, team_id)
    service.require_role(db, team_id, user.id, "owner")
    team.monthly_budget_cents = body.monthly_budget_cents
    db.add(team)
    return {"id": team.user_id, "monthly_budget_cents": team.monthly_budget_cents,
            "month_spent_cents": service.team_spent_this_month(db, team_id)}


# --------------------------------------------------------------- 企业信息与发票
@router.post("/{team_id}/company")
def submit_company(team_id: int, body: CompanyIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """TEAM-030 提交企业信息与营业执照，转人工核验。

    沿用 V76 那套：材料标记为敏感文件，管理员审核后才 `verified`。
    """
    team = _get(db, team_id)
    service.require_role(db, team_id, user.id, "owner")
    if not body.license_images:
        raise bad_request("需上传营业执照影像", "images_required")
    from app.modules.account.cert_service import _mark_images_sensitive

    team.company_name = body.company_name
    team.tax_number = body.tax_number
    team.license_images = ",".join(body.license_images)
    team.verify_status = "pending"
    team.verify_reason = ""
    db.add(team)
    _mark_images_sensitive(db, body.license_images, user.id)
    return _dump(team)
