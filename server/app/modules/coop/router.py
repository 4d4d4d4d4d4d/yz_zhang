"""COOP 早期合作体（50 号 spec）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_verified
from app.core.errors import conflict, forbidden, not_found
from app.modules.account.models import User

from . import compliance_path as cpath
from . import service
from .models import CONTRIBUTION_KINDS, Contribution, Distribution, Venture, VentureMember
from app.core.timefmt import iso

router = APIRouter(prefix="/ventures", tags=["coop"])


class VentureIn(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    purpose: str = Field(default="", max_length=2000)
    category: str = Field(default="", max_length=50)
    risk_disclosure_version: str


class InviteIn(BaseModel):
    user_id: int


class AcceptInviteIn(BaseModel):
    risk_disclosure_version: str


class ContributionIn(BaseModel):
    kind: str = Field(pattern="^(time|money|ip|resource|other)$")
    description: str = Field(min_length=2, max_length=2000)
    evidence: list[str] = Field(default_factory=list)


class ConfirmIn(BaseModel):
    accept: bool = True
    valued_cents: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=1000)


class DistributeIn(BaseModel):
    amount_cents: int = Field(gt=0)
    memo: str = Field(default="", max_length=200)


def _dump(v: Venture) -> dict:
    return {"id": v.user_id, "name": v.name, "purpose": v.purpose,
            "category": v.category, "status": v.status, "founder_id": v.founder_id,
            "created_at": iso(v.created_at)}


def _get(db: Session, venture_id: int) -> Venture:
    v = service.get_venture(db, venture_id)
    if not v:
        raise not_found("合作体不存在")
    return v


def _require_member(db: Session, venture_id: int, user: User) -> None:
    if not service.is_member(db, venture_id, user.id):
        raise forbidden("仅合作体成员可执行此操作")


# ------------------------------------------------------------- 风险揭示书（前置）
@router.get("/risk-disclosure")
def risk_disclosure(name: str = "（待定）"):
    """COOP-030 加入前必须签的那份。**公开可读**——要求人签一份他看不到的
    东西是荒谬的。"""
    return {
        "version": cpath.RISK_DISCLOSURE_VERSION,
        "title": cpath.RISK_DISCLOSURE_TITLE,
        "points": list(cpath.RISK_DISCLOSURE_POINTS),
        "text": cpath.risk_disclosure_text(name),
    }


# ------------------------------------------------------------------------ 合作体
@router.post("", status_code=201)
def create_venture(body: VentureIn, user: User = Depends(require_verified),
                   db: Session = Depends(get_db)):
    """建一个合作体。发起人也要签风险揭示书——**他承担的风险不比别人少**。"""
    if body.risk_disclosure_version != cpath.RISK_DISCLOSURE_VERSION:
        raise conflict("需先签署当前版本的风险揭示书", "risk_disclosure_required")

    # 与 V73「agent 是 User」同一条理由：钱包/托管/合约/纠纷/发任务
    # 全部以 user_id 为键，合作体要有资金池、要能发任务，不复用就得各写第二遍。
    venture_user = User(
        phone=f"venture:{body.name}:{user.id}",
        nickname=body.name, is_venture=True, is_verified=True, is_adult=True,
        accepting_orders=False,      # 合作体是发布方，不接单
    )
    db.add(venture_user)
    db.flush()
    venture = Venture(user_id=venture_user.id, name=body.name, purpose=body.purpose,
                      category=body.category, founder_id=user.id, status="active")
    db.add(venture)
    db.flush()
    service.add_member(db, venture, user, body.risk_disclosure_version, role="founder")
    return _dump(venture)


@router.get("/mine")
def my_ventures(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(VentureMember).filter(VentureMember.user_id == user.id,
                                          VentureMember.active.is_(True)).all()
    out = []
    for m in rows:
        v = service.get_venture(db, m.venture_id)
        if v:
            out.append({**_dump(v), "role": m.role})
    return out


@router.get("/{venture_id}")
def get_venture(venture_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    v = _get(db, venture_id)
    _require_member(db, venture_id, user)
    from app.modules.wallet import service as wallet

    acct = wallet.get_or_create(db, v.user_id)
    return {
        **_dump(v),
        "members": [
            {"user_id": m.user_id, "role": m.role,
             "joined_at": iso(m.joined_at)}
            for m in service.members(db, venture_id)
        ],
        "shares": service.shares_bps(db, venture_id),
        # 「已实现」三个字在这里是字面意思：这就是合作体真的收到的钱
        "realized_funds_cents": acct.available_cents,
    }


# COOP-021 **邀请制，没有公开加入端点。**
# 这不是产品偏好，是让这个模式落在合作内部而非公开募集的结构性设计之一
# （另外两条：只分已实现收益、份额不可转让）。
@router.post("/{venture_id}/invitations", status_code=201)
def invite(venture_id: int, body: InviteIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    v = _get(db, venture_id)
    _require_member(db, venture_id, user)
    invitee = db.get(User, body.user_id)
    if not invitee:
        raise not_found("用户不存在")
    block = service.join_block(db, v, invitee, cpath.RISK_DISCLOSURE_VERSION)
    # 邀请时只检查「结构性」拒绝理由；风险揭示书由**被邀请人自己**签，
    # 不能由邀请人代签——代签的知情同意不是知情同意
    if block and "风险揭示书" not in block:
        raise conflict(block, "invite_blocked")
    from app.modules.notification.service import notify

    notify(db, invitee.id, "system", "合作邀请",
           f"{user.nickname or '一位用户'} 邀请你加入合作体「{v.name}」。"
           f"加入前请阅读并签署风险揭示书。")
    return {"invited": invitee.id, "venture_id": venture_id,
            "risk_disclosure_version": cpath.RISK_DISCLOSURE_VERSION}


@router.post("/{venture_id}/members", status_code=201)
def accept_invite(venture_id: int, body: AcceptInviteIn,
                  user: User = Depends(require_verified), db: Session = Depends(get_db)):
    v = _get(db, venture_id)
    m = service.add_member(db, v, user, body.risk_disclosure_version)
    return {"venture_id": venture_id, "user_id": m.user_id, "role": m.role}


# ------------------------------------------------------------------------ 贡献
@router.post("/{venture_id}/contributions", status_code=201)
def submit_contribution(venture_id: int, body: ContributionIn,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    _get(db, venture_id)
    _require_member(db, venture_id, user)
    row = Contribution(venture_id=venture_id, user_id=user.id, kind=body.kind,
                       description=body.description, evidence=body.evidence)
    db.add(row)
    db.flush()
    # 提交时**没有计价**：贡献人说「我做了什么」，确认人说「这值多少」。
    return {"id": row.id, "status": row.status}


@router.get("/{venture_id}/contributions")
def list_contributions(venture_id: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _get(db, venture_id)
    _require_member(db, venture_id, user)
    rows = (db.query(Contribution).filter(Contribution.venture_id == venture_id)
            .order_by(Contribution.id.desc()).all())
    return [
        {"id": c.id, "user_id": c.user_id, "kind": c.kind, "description": c.description,
         "status": c.status, "valued_cents": c.valued_cents,
         "confirmed_by": c.confirmed_by, "confirm_note": c.confirm_note,
         "evidence": c.evidence,
         "created_at": iso(c.created_at),
         # 客户端的「确认」按钮读这个，与服务端同一判断（单一来源）
         "can_confirm": c.status == "proposed" and c.user_id != user.id}
        for c in rows
    ]


@router.post("/{venture_id}/contributions/{contribution_id}/confirm")
def confirm(venture_id: int, contribution_id: int, body: ConfirmIn,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get(db, venture_id)
    row = db.get(Contribution, contribution_id)
    if not row or row.venture_id != venture_id:
        raise not_found("贡献记录不存在")
    row = service.confirm_contribution(db, row, user, body.valued_cents,
                                       body.note, body.accept)
    return {"id": row.id, "status": row.status, "valued_cents": row.valued_cents,
            "shares": service.shares_bps(db, venture_id)}


@router.get("/{venture_id}/shares")
def shares(venture_id: int, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    _get(db, venture_id)
    _require_member(db, venture_id, user)
    rows = service.shares_bps(db, venture_id)
    return {
        "shares": rows, "total_bps": sum(r["share_bps"] for r in rows),
        # 说清楚它是怎么来的：份额是**算出来的**，不是分配的
        "basis": "份额 = 本人已确认贡献计价 ÷ 全体已确认贡献计价；"
                 "他人后续贡献会稀释你的份额。",
    }


# ------------------------------------------------------------------------ 分配
@router.post("/{venture_id}/distributions", status_code=201)
def distribute(venture_id: int, body: DistributeIn,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = _get(db, venture_id)
    _require_member(db, venture_id, user)
    dist = service.distribute(db, v, user, body.amount_cents, body.memo)
    return {"id": dist.id, "total_cents": dist.total_cents,
            "share_snapshot": dist.share_snapshot}


@router.get("/{venture_id}/distributions")
def list_distributions(venture_id: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    _get(db, venture_id)
    _require_member(db, venture_id, user)
    rows = (db.query(Distribution).filter(Distribution.venture_id == venture_id)
            .order_by(Distribution.id.desc()).all())
    return [{"id": d.id, "total_cents": d.total_cents, "memo": d.memo,
             "share_snapshot": d.share_snapshot,
             "created_at": iso(d.created_at)}
            for d in rows]


# ------------------------------------------------------------------ 合规路径
@router.get("/{venture_id}/compliance-path")
def compliance(venture_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """COOP-040 **告诉你需要什么，不拦住你。**

    合规是路径上的一步：需要什么文件就生成什么，需要什么资质就去办。
    这个端点给的是结构化清单 + 每项的理由 + 当前状态，
    并明确声明它不是法律意见。
    """
    v = _get(db, venture_id)
    _require_member(db, venture_id, user)
    return service.compliance_for(db, v)
