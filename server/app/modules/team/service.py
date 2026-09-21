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


def month_start(now=None):
    """TEAM-054 本月起点，**按 UTC 自然月**。

    平台内部全部是 UTC（V83），也刻意不存用户时区（TZ-065）。
    代价说清楚：东八区的团队，额度在每月 1 日 08:00（当地时间）重置，
    不是 00:00。这个偏差对额度的意义不大，但**要写出来**，
    而不是让人自己发现。
    """
    now = now or utcnow()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _spent_since(db: Session, team_id: int, since, user_id: int | None = None) -> int:
    """TEAM-053 只算**已执行**的。

    审批期间不预扣（TEAM-022 的既有判断），所以「已批准未执行」还没花钱，
    不该占额度；但正因为如此，执行时必须**再判一次**——
    审批到执行之间，世界会变。
    """
    q = (
        db.query(SpendRequest)
        .filter(SpendRequest.team_id == team_id,
                SpendRequest.status == "executed",
                SpendRequest.created_at >= since)
    )
    if user_id is not None:
        q = q.filter(SpendRequest.requester_id == user_id)
    return sum(r.amount_cents for r in q.all())


def member_spent_this_month(db: Session, team_id: int, user_id: int) -> int:
    return _spent_since(db, team_id, month_start(), user_id)


def team_spent_this_month(db: Session, team_id: int) -> int:
    return _spent_since(db, team_id, month_start())


def pool_block(db: Session, team: Team, amount_cents: int) -> str:
    """TEAM-052 团队月度预算池；空串表示还在池子里。

    **对所有路径生效**，包括已被 admin 批准的申请，也包括 owner 自己：
    审批权限不能突破总量——要突破就去改池子，那是一个留痕的、显式的动作，
    而不是审批时顺手放过去。
    """
    if team.monthly_budget_cents <= 0:
        return ""                      # 0 = 不设池，既有团队行为不变
    used = team_spent_this_month(db, team.user_id)
    left = team.monthly_budget_cents - used
    if amount_cents > left:
        return (f"超出团队本月预算池（本月已用 ¥{used / 100:.2f}，"
                f"剩余 ¥{max(0, left) / 100:.2f}）")
    return ""


def spend_block(db: Session, team: Team, member: TeamMember, amount_cents: int) -> str:
    """TEAM-050 这笔支出能不能**自助**花（不经审批）；空串表示可以。

    单一判断来源：客户端的「需要审批」提示与服务端走同一个函数。

    额度是**月度累计**的，不是单笔的——改造前只判单笔，于是同一笔申请
    发 20 次就能零审批划走 20 倍的钱（探针实测）。
    """
    if not team.active:
        return "团队已停用"
    # 预算池排在最前：它是总量约束，谁都绕不过（包括 owner）
    pool = pool_block(db, team, amount_cents)
    if pool:
        return pool
    # TEAM-051 owner 豁免个人额度是**讲得通**的：他就是定额度的那个人，
    # 给他设限不增加任何安全性（他随手调高即可）。
    # 但 admin 豁免讲不通——**admin 是被授予权限的人，不是授予权限的人**。
    if member.role == "owner":
        return ""
    used = member_spent_this_month(db, team.user_id, member.user_id)
    left = member.spend_limit_cents - used
    if amount_cents > left:
        # 提示要说**还剩多少**，不是只说「超额」：
        # 只说超额的话，对方不知道该改金额还是该走审批
        return (f"超出你本月额度（额度 ¥{member.spend_limit_cents / 100:.2f}，"
                f"已用 ¥{used / 100:.2f}，剩余 ¥{max(0, left) / 100:.2f}），需管理员审批")
    return ""


def approvers(db: Session, team_id: int, exclude_user_id: int | None = None) -> list[int]:
    """能审批这个团队支出的人。

    与 `decide_spend` 的判断同源——**自己不能批自己**，所以发起人本人
    不在通知名单里（给他发一条「等你审批」是纯噪音）。
    """
    rows = (
        db.query(TeamMember)
        .filter(TeamMember.team_id == team_id, TeamMember.active.is_(True),
                TeamMember.role.in_(("owner", "admin")))
        .all()
    )
    return [m.user_id for m in rows if m.user_id != exclude_user_id]


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


def notify_pending(db: Session, team: Team, req: SpendRequest, requester: User) -> None:
    """TEAM-060 告诉审批人有东西等他批。

    改造前这里什么都不发：员工的活被卡住，而**卡住他的那个人从头到尾
    不知道**。这笔申请可以一直躺着——没有超时，也没有催办。
    """
    from app.modules.notification.service import notify

    for uid in approvers(db, team.user_id, exclude_user_id=req.requester_id):
        notify(db, uid, "team", "支出待审批",
               f"{requester.nickname} 申请从「{team.name}」支出 "
               f"¥{req.amount_cents / 100:.2f}（{req.purpose or '未填用途'}），等待你审批。")


def notify_decided(db: Session, team: Team, req: SpendRequest) -> None:
    """TEAM-061 把审批结果——**连同那段被强制写下的理由**——送到发起人面前。

    服务端强制驳回必须写原因（`reason_required`），然后把这段话存进
    `decision_reason` 就不管了：发起人不主动再拉一次支出列表就看不到。
    **「必须写」和「送到了」是两件事**（V89 的「必须选」和「看得见」同一条）。

    理由的全部价值在于被驳回的人读到它——他要据此决定是改金额、改用途，
    还是去跟老板谈。送不到，这条强制就只是给审批人加了一道手续。
    """
    from app.modules.notification.service import notify

    if req.status == "approved":
        body = (f"你从「{team.name}」申请的 ¥{req.amount_cents / 100:.2f} 已获批准，"
                f"可以在支出列表里执行。")
    else:
        body = (f"你从「{team.name}」申请的 ¥{req.amount_cents / 100:.2f} 被驳回："
                f"{req.decision_reason}")
    notify(db, req.requester_id, "team", "支出审批结果", body)


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
    team = db.get(Team, req.team_id)
    if team:
        notify_decided(db, team, req)
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
    # TEAM-053 预算池**在执行时再判一次**。
    # 不判的话有条明显的缝：批准 10 笔、逐个执行，池子形同虚设。
    # 这与下面那条「余额是否仍然够」是同一类检查、同一个理由：
    # **审批到执行之间，世界会变。**
    team = db.get(Team, req.team_id)
    pool = pool_block(db, team, req.amount_cents) if team else ""
    if pool:
        raise bad_request(pool + "；请调整本月预算池后再执行", "monthly_budget_exceeded")
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
