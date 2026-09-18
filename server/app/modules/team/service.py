"""TEAM 权限、额度与审批（53 号 spec）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict, forbidden
from app.modules.account.models import User, utcnow
from app.modules.wallet import service as wallet

from .models import SpendRequest, Team, TeamMember


def member_of(db: Session, team_id: int, user_id: int) -> TeamMember | None:
    return (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.user_id == user_id,
                TeamMember.active.is_(True))
        .first()
    )


def require_member(db: Session, team_id: int, user_id: int) -> TeamMember:
    m = member_of(db, team_id, user_id)
    if not m:
        raise forbidden("非团队成员")
    return m


def require_role(db: Session, team_id: int, user_id: int, *allowed: str) -> TeamMember:
    m = require_member(db, team_id, user_id)
    if m.role not in allowed:
        raise forbidden(f"需要 {'/'.join(allowed)} 权限", "insufficient_role")
    return m


def spend_block(db: Session, team: Team, member: TeamMember, amount_cents: int) -> str:
    """TEAM-011 这笔支出能不能直接花；空串表示可以。

    单一判断来源：客户端的「需要审批」提示与服务端走同一个函数。
    """
    if not team.active:
        return "团队已停用"
    # owner 无额度限制——他就是那个定额度的人，给他设限没有意义
    if member.role == "owner":
        return ""
    if member.role == "admin":
        return ""
    if amount_cents > member.spend_limit_cents:
        return (f"超出你的单笔额度（¥{member.spend_limit_cents / 100:.2f}），"
                f"需管理员审批")
    return ""


def create_spend_request(db: Session, team: Team, user: User, amount_cents: int,
                         purpose: str, task_id: int | None = None) -> SpendRequest:
    if amount_cents <= 0:
        raise bad_request("金额必须为正", "invalid_amount")
    require_member(db, team.user_id, user.id)
    row = SpendRequest(team_id=team.user_id, requester_id=user.id,
                       amount_cents=amount_cents, purpose=purpose, task_id=task_id)
    db.add(row)
    db.flush()
    # 审批期间**不动钱**（见 models 里的理由）
    return row


def decide_spend(db: Session, req: SpendRequest, decider: User, approve: bool,
                 reason: str) -> SpendRequest:
    """TEAM-020/021 审批。**不能自己批自己的。**

    与 COOP-010（贡献不能自己确认）、VER-021（当事人不能核验）同一条规矩。
    """
    if req.status != "pending":
        raise conflict("该申请已处理", "already_decided")
    require_role(db, req.team_id, decider.id, "owner", "admin")
    if req.requester_id == decider.id:
        raise forbidden("不能审批自己发起的支出", "self_approval")
    if not approve and not reason.strip():
        raise bad_request("驳回必须写明原因", "reason_required")
    req.status = "approved" if approve else "rejected"
    req.decided_by = decider.id
    req.decision_reason = reason
    req.decided_at = utcnow()
    db.add(req)
    return req


def execute_spend(db: Session, req: SpendRequest, actor: User) -> dict:
    """把已批准的支出真正划给发起人，让他去发任务/托管。

    TEAM-022 这一步可能失败：审批期间没预扣，批准到执行之间团队余额
    可能已被别的支出用掉。**明确报错**，不产生半截状态。
    """
    if req.status != "approved":
        raise conflict("该申请尚未批准或已执行", "not_approved")
    if req.requester_id != actor.id:
        raise forbidden("仅发起人可执行自己的支出申请")
    team_acct = wallet.get_or_create(db, req.team_id)
    if team_acct.available_cents < req.amount_cents:
        raise bad_request(
            f"团队可用资金不足（当前 ¥{team_acct.available_cents / 100:.2f}）。"
            f"审批期间不预扣资金，期间可能已被其他支出占用。",
            "insufficient_team_funds",
        )
    wallet.transfer(db, req.team_id, req.requester_id, req.amount_cents, None,
                    memo=f"团队支出 #{req.id}：{req.purpose}", kind="team_spend")
    req.status = "executed"
    db.add(req)
    return {"id": req.id, "status": req.status, "amount_cents": req.amount_cents}


def can_invoice(team: Team) -> str:
    """TEAM-030 能不能开票；空串表示可以。

    **未核验的企业信息不能开票**——一张开给未核验抬头的发票，
    是税务风险不是便利。
    """
    if team.verify_status != "verified":
        return "团队企业信息尚未通过核验，暂不能开具发票"
    if not team.company_name or not team.tax_number:
        return "缺少企业名称或税号"
    return ""
