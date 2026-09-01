"""管理后台 API（12.E）：用户管理、举报处置队列、平台指标看板。"""
from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, forbidden, not_found
from app.core.locks import job_slot
from app.modules.account.models import User
from app.modules.content.models import Content
from app.modules.contract.models import Contract
from app.modules.dispute.models import Dispute
from app.modules.task.models import Task

from .models import AdminAudit, Report

router = APIRouter(tags=["admin"])


def record_audit(db, admin_id: int, action: str, target_type: str = "",
                 target_id: int | None = None, detail: str = "") -> None:
    """OPS-012 管理员操作审计留痕（高权限动作统一调用）。"""
    db.add(AdminAudit(admin_id=admin_id, action=action, target_type=target_type,
                      target_id=target_id, detail=detail[:500]))


class UnbanIn(BaseModel):
    ip: str = Field(min_length=3, max_length=64)


@router.get("/admin/security")
def security_board(_: User = Depends(require_admin)):
    """SECEV-020 安全看板：全局封禁列表、观察名单与人机验证触发次数。

    **读 DB，所以任何副本看到的都一样。** 改造前它读的是进程内 dict——
    三副本部署下管理员只能看到当前这个副本封了谁，另外两个完全不知道。
    """
    from app.core import guard

    return guard.board()


@router.post("/admin/security/unban")
def security_unban(body: UnbanIn, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """SECEV-021 解除封禁（误封公司出口 IP 时的补救手段）。

    改造前解封只作用于当前副本：被误封的公司出口 IP 之后还有 (N-1)/N 的概率
    被拒，用户报「有时候能登录有时候不能」，客服根本复现不出来。
    """
    from app.core import guard

    guard.unban(db, body.ip, admin.id)
    record_audit(db, admin.id, "security_unban", "ip", 0, f"解封 {body.ip}")
    return {"ip": body.ip, "banned": False}


@router.get("/admin/vendors")
def vendor_status(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """VND-041 供应商健康面板：各能力当前实现、是否仍是模拟、熔断状态、
    近 24h 成功率。生产环境若有 P0 能力仍是模拟实现，这里显式列出（上线阻塞项）。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow
    from app.vendors.models import VendorCall
    from app.vendors.registry import missing_production_providers, status

    since = utcnow() - timedelta(hours=24)
    rows = (
        db.query(VendorCall.kind, VendorCall.status, func.count(VendorCall.id))
        .filter(VendorCall.created_at >= since)
        .group_by(VendorCall.kind, VendorCall.status)
        .all()
    )
    stats: dict[str, dict[str, int]] = {}
    for kind, st, cnt in rows:
        stats.setdefault(kind, {})[st] = int(cnt)

    out = []
    for item in status():
        counts = stats.get(item["kind"], {})
        total = sum(counts.values())
        ok = counts.get("succeeded", 0)
        out.append({**item, "calls_24h": total,
                    "success_rate": round(ok / total, 4) if total else None})
    return {"vendors": out, "blocking_for_production": missing_production_providers()}


@router.get("/admin/audit-log")
def audit_log(
    action: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    """OPS-012 审计日志查询（管理员）。"""
    query = db.query(AdminAudit)
    if action:
        query = query.filter(AdminAudit.action == action)
    rows = query.order_by(AdminAudit.id.desc()).offset(offset).limit(limit).all()
    return [
        {"id": r.id, "admin_id": r.admin_id, "action": r.action,
         "target_type": r.target_type, "target_id": r.target_id,
         "detail": r.detail, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


class ReportIn(BaseModel):
    target_type: str
    target_id: int
    reason: str = Field(min_length=2, max_length=500)


class ResolveIn(BaseModel):
    action: str  # dismiss / remove_content / ban_user


# ---------- 举报（普通用户入口，RISK-007） ----------
@router.post("/reports", status_code=201)
def create_report(body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.target_type not in ("task", "content", "user", "message"):
        raise bad_request("非法举报对象", "invalid_target")
    row = Report(reporter_id=user.id, **body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id, "status": row.status}


# ---------- 审核队列（RISK-002） ----------
@router.get("/admin/reports")
def report_queue(
    status: str = "pending", admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    rows = db.query(Report).filter(Report.status == status).order_by(Report.id).limit(100).all()
    return [
        {"id": r.id, "reporter_id": r.reporter_id, "target_type": r.target_type,
         "target_id": r.target_id, "reason": r.reason, "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.post("/admin/reports/{report_id}/resolve")
def resolve_report(
    report_id: int, body: ResolveIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """处置留痕（RISK-002/006）：驳回 / 下架内容 / 封禁用户。"""
    report = db.get(Report, report_id)
    if not report or report.status != "pending":
        raise not_found("举报不存在或已处理")
    if body.action not in ("dismiss", "remove_content", "ban_user"):
        raise bad_request("非法处置动作", "invalid_action")
    if body.action == "remove_content":
        if report.target_type == "content":
            content = db.get(Content, report.target_id)
            if content:
                content.status = "removed"
                db.add(content)
        elif report.target_type == "task":
            task = db.get(Task, report.target_id)
            if task and task.status in ("draft", "published"):
                task.status = "cancelled"
                db.add(task)
    elif body.action == "ban_user":
        target_user_id = report.target_id
        if report.target_type == "content":
            content = db.get(Content, report.target_id)
            target_user_id = content.author_id if content else 0
        user = db.get(User, target_user_id)
        if user:
            user.is_banned = True
            db.add(user)
    report.status = "resolved"
    report.action = body.action
    report.handled_by = admin.id
    db.add(report)
    return {"id": report.id, "status": "resolved", "action": body.action}


# ---------- 工单处理（CS-010/013） ----------
class TicketResolveIn(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


@router.get("/admin/tickets")
def ticket_queue(status: str = "open", admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.modules.support.models import Ticket

    rows = db.query(Ticket).filter(Ticket.status == status).order_by(Ticket.id).limit(100).all()
    return [
        {"id": t.id, "user_id": t.user_id, "subject": t.subject, "body": t.body,
         "created_at": t.created_at.isoformat()}
        for t in rows
    ]


@router.post("/admin/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: int, body: TicketResolveIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    from app.modules.account.models import utcnow
    from app.modules.notification.service import notify
    from app.modules.support.models import Ticket

    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.status != "open":
        raise not_found("工单不存在或已处理")
    ticket.status = "resolved"
    ticket.reply = body.reply
    ticket.handler_id = admin.id
    ticket.resolved_at = utcnow()
    db.add(ticket)
    notify(db, ticket.user_id, "system", "工单已处理", f"「{ticket.subject}」：{body.reply[:100]}")
    return {"id": ticket.id, "status": "resolved"}


# ---------- 用户管理（OPS-002） ----------
@router.get("/admin/users")
def list_users(
    q: str | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    query = db.query(User)
    if q:
        query = query.filter(User.nickname.contains(q) | User.phone.contains(q))
    rows = query.order_by(User.id).limit(limit).all()
    return [
        {"id": u.id, "phone": u.phone, "nickname": u.nickname, "is_verified": u.is_verified,
         "is_banned": u.is_banned, "credit_score": u.credit_score, "tasks_completed": u.tasks_completed}
        for u in rows
    ]


def _ban_impact(db, user_id: int) -> dict:
    """OPS-013 封禁影响面：在途合约 / 托管资金 / 钱包余额。

    封禁会让该用户无法交付或验收，其对手方的托管资金将被无限期困住——
    封禁前必须让管理员看见这个爆炸半径。
    """
    from app.modules.wallet.service import get_or_create

    in_flight = (
        db.query(Contract)
        .filter(
            (Contract.requester_id == user_id) | (Contract.executor_id == user_id),
            Contract.status.in_(("pending_signatures", "signed", "funded")),
        )
        .all()
    )
    acct = get_or_create(db, user_id)
    # 未成交的挂单：封禁后无人能选人，须下架，否则工人白报名空等
    open_tasks = (
        db.query(Task)
        .filter(Task.creator_id == user_id, Task.status.in_(("draft", "published")))
        .all()
    )
    return {
        "in_flight_contracts": [
            {"contract_id": c.id, "task_id": c.task_id, "status": c.status,
             "amount_cents": c.amount_cents,
             "counterparty_id": c.executor_id if c.requester_id == user_id else c.requester_id}
            for c in in_flight
        ],
        "in_flight_count": len(in_flight),
        "escrow_at_risk_cents": sum(
            c.amount_cents - c.released_cents for c in in_flight if c.status == "funded"
        ),
        "open_task_ids": [t.id for t in open_tasks],
        "open_task_count": len(open_tasks),
        "wallet": {"available_cents": acct.available_cents,
                   "escrow_cents": acct.escrow_cents, "frozen_cents": acct.frozen_cents},
    }


@router.get("/admin/users/{user_id}/ban-impact")
def ban_impact(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """OPS-013 封禁前预览影响面（不产生副作用）。"""
    if not db.get(User, user_id):
        raise not_found("用户不存在")
    return _ban_impact(db, user_id)


@router.post("/admin/users/{user_id}/ban")
def ban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    if user.is_admin:
        raise bad_request("不能封禁管理员", "cannot_ban_admin")
    impact = _ban_impact(db, user_id)
    user.is_banned = True
    db.add(user)
    # OPS-013 通知在途合约的对手方：被封用户无法再交付/验收，
    # 请及时取消或发起纠纷，避免托管资金无限期困住。
    from app.modules.notification.service import notify

    for c in impact["in_flight_contracts"]:
        notify(db, c["counterparty_id"], "task", "对方账号已被封禁",
               f"任务 #{c['task_id']}（合约 #{c['contract_id']}）的对方账号已被平台封禁，"
               "无法继续履约。请尽快取消任务或发起纠纷，以便结清托管资金。")
    # OPS-013 下架未成交挂单：封禁后无人能选人，留在广场只会让工人白报名空等
    from app.modules.task.models import Application
    from app.modules.task.service import transition

    for task_id in impact["open_task_ids"]:
        task = db.get(Task, task_id)
        if not task:
            continue
        pending = db.query(Application).filter(
            Application.task_id == task_id, Application.status == "pending"
        ).all()
        for a in pending:
            a.status = "rejected"
            db.add(a)
            notify(db, a.applicant_id, "task", "报名的任务已下架",
                   f"《{task.title}》的发布方账号已被封禁，任务已下架，你的报名已自动关闭。")
        transition(db, task, "cancelled", {"cancelled_by": "system_creator_banned"})
    record_audit(db, admin.id, "ban_user", "user", user_id,
                 f"在途合约 {impact['in_flight_count']} 笔，涉险托管 {impact['escrow_at_risk_cents']} 分，"
                 f"下架挂单 {impact['open_task_count']} 个")
    return {"id": user.id, "is_banned": True, "impact": impact}


@router.post("/admin/users/{user_id}/unban")
def unban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    user.is_banned = False
    db.add(user)
    record_audit(db, admin.id, "unban_user", "user", user_id)
    return {"id": user.id, "is_banned": False}


# ---------- 类目管理（OPS-004） ----------
class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    required_cert: str = ""


@router.post("/admin/categories", status_code=201)
def create_category(body: CategoryIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.modules.task.models import Category

    if db.query(Category).filter(Category.name == body.name).first():
        raise bad_request("类目已存在", "category_exists")
    row = Category(name=body.name, required_cert=body.required_cert)
    db.add(row)
    db.flush()
    return {"id": row.id, "name": row.name}


@router.patch("/admin/categories/{category_id}")
def update_category(
    category_id: int, active: bool | None = None, required_cert: str | None = None,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    from app.modules.task.models import Category

    row = db.get(Category, category_id)
    if not row:
        raise not_found("类目不存在")
    if active is not None:
        row.active = active
    if required_cert is not None:
        row.required_cert = required_cert
    db.add(row)
    return {"id": row.id, "name": row.name, "active": row.active, "required_cert": row.required_cert}


# ---------- 匹配策略配置（MATCH-008） ----------
class WeightsIn(BaseModel):
    skill: float = Field(ge=0, le=1)
    credit: float = Field(ge=0, le=1)
    distance: float = Field(ge=0, le=1)
    rating: float = Field(ge=0, le=1)


@router.get("/admin/matching-config")
def get_matching_config(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.modules.matching.service import get_weights

    return {"weights": get_weights(db)}


@router.put("/admin/matching-config")
def set_matching_config(
    body: WeightsIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    total = body.skill + body.credit + body.distance + body.rating
    if abs(total - 1.0) > 0.001:
        raise bad_request(f"权重之和必须为 1（当前 {total:.3f}）", "weights_sum_invalid")
    from app.modules.matching.models import MatchingConfig

    row = db.get(MatchingConfig, "weights")
    if not row:
        row = MatchingConfig(key="weights", data={})
        db.add(row)
    row.data = body.model_dump()
    db.add(row)
    return {"weights": row.data}


# ---------- 城市开通管理（GEO-030） ----------
class CityIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)


@router.post("/admin/cities", status_code=201)
def open_city(body: CityIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.modules.task.models import City

    existing = db.query(City).filter(City.name == body.name).first()
    if existing:
        existing.active = True
        db.add(existing)
        return {"id": existing.id, "name": existing.name, "active": True}
    row = City(name=body.name)
    db.add(row)
    db.flush()
    return {"id": row.id, "name": row.name, "active": True}


@router.patch("/admin/cities/{city_id}")
def toggle_city(
    city_id: int, active: bool, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    from app.modules.task.models import City

    row = db.get(City, city_id)
    if not row:
        raise not_found("城市不存在")
    row.active = active
    db.add(row)
    return {"id": row.id, "name": row.name, "active": row.active}


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(default="", max_length=2000)
    verified_only: bool = False  # 仅通知已实名用户（如资金/合规类公告）


@router.post("/admin/announcements")
def broadcast_announcement(
    body: AnnouncementIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """OPS-009 平台公告：向全体（或已实名）活跃用户广播站内通知。"""
    from app.modules.notification.service import notify

    q = db.query(User).filter(User.is_deleted.is_(False), User.is_banned.is_(False))
    if body.verified_only:
        q = q.filter(User.is_verified.is_(True))
    count = 0
    for u in q:
        notify(db, u.id, "announcement", body.title, body.body)
        count += 1
    return {"delivered": count}


# ---------- 平台收入结算（OPS-010） ----------
class SettleIn(BaseModel):
    amount_cents: int = Field(gt=0)
    memo: str = "平台收入结算"


@router.get("/admin/platform-finance")
def platform_finance(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """平台收入总览：累计佣金（实收）、已结算、可结算余额。"""
    from app.modules.wallet import service as wallet

    return wallet.platform_finance(db)


@router.post("/admin/platform-finance/settle")
def settle_platform(
    body: SettleIn, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """OPS-010 平台收入结算：把平台账户余额划出（模拟对公结算）。"""
    from app.modules.wallet import service as wallet

    result = wallet.settle_platform(db, body.amount_cents, body.memo)
    record_audit(db, admin.id, "platform_settle", "platform", None,
                 f"结算 {body.amount_cents} 分：{body.memo}")
    return result


# ---------- 对账 job（PAY-006/008） ----------
def _job_or_admin(
    x_job_token: str = Header(default=""),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db),
) -> int:
    """JOB-020 调度器（X-Job-Token）**或**管理员都能触发，返回触发者 id（调度器为 0）。

    此前它只接受 `require_admin`——**调度器根本调不动**，加上又不在调度表里，
    这个「日终对账」实际上是一个需要有人每天记得手动点的按钮。
    这门生意最重要的那道安全网，从来没有被架起来过。
    """
    if x_job_token and x_job_token == settings.JOB_TOKEN:
        return 0                       # 平台账户，见 JOB-021
    from app.core.deps import get_current_user

    user = get_current_user(db=db, authorization=authorization)
    if not user.is_admin:
        raise forbidden("需要管理员权限", "admin_required")
    return user.id


@router.post("/admin/jobs/reconcile")
def run_reconcile(triggered_by: int = Depends(_job_or_admin),
                  db: Session = Depends(get_db),
                  __=Depends(job_slot("reconcile"))):
    """PAY-008 告警闭环：对账不平不能只返回结果——自动开差错工单 + 通知全体管理员。"""
    from app.modules.notification.service import notify
    from app.modules.risk.service import reconcile
    from app.modules.support.models import Ticket

    result = reconcile(db)
    if not result["ok"]:
        detail = "; ".join(str(m) for m in result["mismatches"])[:1500]
        # JOB-021 调度器触发时归属平台账户（0），而不是某个碰巧在场的管理员
        db.add(Ticket(user_id=triggered_by, subject="[对账差错] 资金不变量校验失败",
                      body=f"日终对账发现差错，请立即核查：{detail}"))
        for a in db.query(User).filter(User.is_admin.is_(True)).all():
            notify(db, a.id, "risk", "对账差错告警",
                   "资金对账不变量校验失败，差错工单已生成，请立即处理。")
    return result


# ---------- 数据看板（OPS-007） ----------
@router.get("/admin/metrics")
def metrics(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    verified_users = db.query(User).filter(User.is_verified.is_(True)).count()
    total_tasks = db.query(Task).count()
    published = db.query(Task).filter(Task.status == "published").count()
    completed = db.query(Task).filter(Task.status == "completed").count()
    disputed = db.query(Dispute).count()
    gmv = db.query(func.coalesce(func.sum(Contract.released_cents), 0)).scalar()
    # SC-009 佣金收入以平台账户实收为准（含纠纷/取消场景、无取整漂移），
    # 而非按 Σreleased×费率估算（会漏计纠纷/取消佣金）
    from app.modules.wallet import service as wallet

    fee_income = wallet.platform_finance(db)["total_fee_cents"]
    closed_loop_rate = round(completed / total_tasks, 4) if total_tasks else 0.0
    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "total_tasks": total_tasks,
        "published_tasks": published,
        "completed_tasks": completed,
        "closed_loop_rate": closed_loop_rate,  # 北极星指标（15 号 spec）
        "dispute_count": disputed,
        "gmv_cents": int(gmv),
        "fee_income_cents": int(fee_income),
    }
