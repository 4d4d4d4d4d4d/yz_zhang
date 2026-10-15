"""管理后台 API（12.E）：用户管理、举报处置队列、平台指标看板。"""
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.locks import job_slot
from app.modules.account.models import User, utcnow
from app.modules.content.models import Content
from app.modules.contract.models import Contract
from app.modules.dispute.models import Dispute
from app.modules.task.models import Task

from .models import AdminAudit, Report
from app.core.timefmt import UtcDatetime, iso
from app.core.admin_roles import ANY, require_role

router = APIRouter(tags=["admin"])


def record_audit(db, admin_id: int, action: str, target_type: str = "",
                 target_id: int | None = None, detail: str = "") -> None:
    """OPS-012 管理员操作审计留痕（高权限动作统一调用）。ADMIN-062 起每条进哈希链（149 号 spec）。"""
    from .audit_chain import append

    append(db, AdminAudit(admin_id=admin_id, action=action, target_type=target_type,
                          target_id=target_id, detail=detail[:500]))


class UnbanIn(BaseModel):
    ip: str = Field(min_length=3, max_length=64)


@router.get("/admin/security")
def security_board(_: User = Depends(require_role("compliance"))):
    """SECEV-020 安全看板：全局封禁列表、观察名单与人机验证触发次数。

    **读 DB，所以任何副本看到的都一样。** 改造前它读的是进程内 dict——
    三副本部署下管理员只能看到当前这个副本封了谁，另外两个完全不知道。
    """
    from app.core import guard

    return guard.board()


@router.post("/admin/security/unban")
def security_unban(body: UnbanIn, admin: User = Depends(require_role("compliance")),
                   db: Session = Depends(get_db, scope="function")):
    """SECEV-021 解除封禁（误封公司出口 IP 时的补救手段）。

    改造前解封只作用于当前副本：被误封的公司出口 IP 之后还有 (N-1)/N 的概率
    被拒，用户报「有时候能登录有时候不能」，客服根本复现不出来。
    """
    from app.core import guard

    guard.unban(db, body.ip, admin.id)
    record_audit(db, admin.id, "security_unban", "ip", 0, f"解封 {body.ip}")
    return {"ip": body.ip, "banned": False}


@router.get("/admin/vendors")
def vendor_status(db: Session = Depends(get_db, scope="function"), _: User = Depends(require_role(*ANY))):
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
    from app.core.commercial import report
    return {"vendors": out, "blocking_for_production": missing_production_providers(),
            "commercial_readiness": report()}


def _audit_query(db: Session, action: str | None, admin_id: int | None, target_type: str | None,
                 target_id: int | None, since, until, q: str | None):
    """ADMIN-061 审计日志的筛选（143 号 spec）：查询与导出共用同一套条件，导出的就是界面上筛出来的。"""
    query = db.query(AdminAudit)
    if action:
        query = query.filter(AdminAudit.action == action)
    if admin_id is not None:
        query = query.filter(AdminAudit.admin_id == admin_id)
    if target_type:
        query = query.filter(AdminAudit.target_type == target_type)
    if target_id is not None:
        query = query.filter(AdminAudit.target_id == target_id)
    if since is not None:
        query = query.filter(AdminAudit.created_at >= since)
    if until is not None:
        query = query.filter(AdminAudit.created_at < until)
    if q:
        query = query.filter(AdminAudit.detail.contains(q))
    return query


AUDIT_EXPORT_MAX = 10_000


@router.get("/admin/audit-log")
def audit_log(
    response: Response,
    action: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    admin_id: int | None = None,
    target_type: str | None = Query(default=None, max_length=40),
    target_id: int | None = None,
    since: UtcDatetime | None = None,
    until: UtcDatetime | None = None,
    q: str | None = Query(default=None, max_length=100),
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """OPS-012 审计日志查询（管理员）。ADMIN-061 起可按管理员、对象、时间段、说明里的字筛选；
    总条数在响应头 `X-Total-Count`（响应体仍是数组，原有调用方不受影响）。"""
    query = _audit_query(db, action, admin_id, target_type, target_id, since, until, q)
    response.headers["X-Total-Count"] = str(query.count())
    rows = query.order_by(AdminAudit.id.desc()).offset(offset).limit(limit).all()
    return [
        {"id": r.id, "admin_id": r.admin_id, "action": r.action,
         "target_type": r.target_type, "target_id": r.target_id,
         "detail": r.detail, "created_at": iso(r.created_at)}
        for r in rows
    ]


@router.get("/admin/audit-log/verify")
def verify_audit_log(admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function")):
    """ADMIN-062 审计日志自检（149 号 spec）：从链上第一条走到链头，指出第一处断点。自检本身也进审计。"""
    from .audit_chain import verify

    out = verify(db)
    record_audit(db, admin.id, "verify_audit_log", "audit_log", None,
                 f"{'完整' if out['ok'] else '有断点'}，检查 {out['checked']} 条")
    db.commit()
    return out


@router.get("/admin/audit-log/export")
def export_audit_log(
    action: str | None = None,
    admin_id: int | None = None,
    target_type: str | None = Query(default=None, max_length=40),
    target_id: int | None = None,
    since: UtcDatetime | None = None,
    until: UtcDatetime | None = None,
    q: str | None = Query(default=None, max_length=100),
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """ADMIN-061 导出 CSV（监管调取、内审）。时间是北京时间并在表头写明（TZ-068）；
    最多 1 万行，超出写明「已截断」；**导出本身也进审计**——谁在什么时候拿走了哪一段。"""
    import csv
    import io

    from app.core.timefmt import EXPORT_TZ_LABEL, export_time

    query = _audit_query(db, action, admin_id, target_type, target_id, since, until, q)
    total = query.count()
    rows = query.order_by(AdminAudit.id.desc()).limit(AUDIT_EXPORT_MAX).all()
    names = {u.id: u.nickname for u in db.query(User).filter(User.id.in_({r.admin_id for r in rows} or {-1}))}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"时间（{EXPORT_TZ_LABEL}）", "管理员编号", "管理员昵称", "动作", "对象类型", "对象编号", "说明"])
    for r in rows:
        w.writerow([export_time(r.created_at), r.admin_id, names.get(r.admin_id, ""), r.action,
                    r.target_type, "" if r.target_id is None else r.target_id, r.detail])
    cond = {k: v for k, v in {"action": action, "admin_id": admin_id, "target_type": target_type,
                              "target_id": target_id, "since": iso(since), "until": iso(until), "q": q}.items() if v}
    record_audit(db, admin.id, "export_audit_log", "audit_log", None, f"{len(rows)} 行；条件 {cond}")
    db.commit()
    return {"filename": "audit-log.csv", "rows": len(rows), "total": total,
            "truncated": total > len(rows), "timezone": EXPORT_TZ_LABEL, "csv": buf.getvalue()}


class ReportIn(BaseModel):
    target_type: str
    target_id: int
    reason: str = Field(min_length=2, max_length=500)


class ResolveIn(BaseModel):
    action: str  # dismiss / remove_content / ban_user


# ---------- 举报（普通用户入口，RISK-007） ----------
@router.post("/reports", status_code=201)
def create_report(body: ReportIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    if body.target_type not in ("task", "content", "user", "message"):
        raise bad_request("非法举报对象", "invalid_target")
    row = Report(reporter_id=user.id, **body.model_dump())
    db.add(row)
    db.flush()
    return {"id": row.id, "status": row.status}


# ---------- 审核队列（RISK-002） ----------
@router.get("/admin/reports")
def report_queue(
    status: str = "pending", admin: User = Depends(require_role("support", "compliance")), db: Session = Depends(get_db, scope="function")
):
    rows = db.query(Report).filter(Report.status == status).order_by(Report.id).limit(100).all()
    return [
        {"id": r.id, "reporter_id": r.reporter_id, "target_type": r.target_type,
         "target_id": r.target_id, "reason": r.reason, "created_at": iso(r.created_at)}
        for r in rows
    ]


@router.post("/admin/reports/{report_id}/resolve")
def resolve_report(
    report_id: int, body: ResolveIn, admin: User = Depends(require_role("support", "compliance")), db: Session = Depends(get_db, scope="function")
):
    """处置留痕（RISK-002/006）：驳回 / 下架内容 / 封禁用户。"""
    report = db.get(Report, report_id)
    if not report or report.status != "pending":
        raise not_found("举报不存在或已处理")
    if body.action not in ("dismiss", "remove_content", "ban_user"):
        raise bad_request("非法处置动作", "invalid_action")
    # MOD-001 处置副作用全部走 admin/service 的单一实现。
    # 此前这里是两行 `user.is_banned = True`——影响面、对手方通知、报名关闭、
    # 挂单下架、审计一件都没做，而**审核队列恰恰是审核员日常真正在用的界面**。
    from . import service as admin_service

    reason = f"举报处置 #{report.id}：{report.reason[:80]}"
    detail = {}
    if body.action == "remove_content":
        if report.target_type == "content":
            detail = admin_service.takedown_content(db, admin.id, report.target_id, reason)
        elif report.target_type == "task":
            detail = admin_service.takedown_task(db, admin.id, report.target_id, reason)
    elif body.action == "ban_user":
        target_user_id = report.target_id
        if report.target_type == "content":
            content = db.get(Content, report.target_id)
            target_user_id = content.author_id if content else 0
        if target_user_id:
            detail = admin_service.ban_user(db, admin.id, target_user_id, reason)
    report.status = "resolved"
    report.action = body.action
    report.handled_by = admin.id
    db.add(report)
    # MOD-004 每一次处置都记审计，**包括驳回**——谁在什么时候驳回了哪条举报，
    # 是事后复盘的关键。只写 report.handled_by 不够：审计日志按动作查询时看不到它
    record_audit(db, admin.id, f"report_{body.action}", report.target_type,
                 report.target_id, f"举报 #{report.id}：{report.reason[:200]}")
    return {"id": report.id, "status": "resolved", "action": body.action,
            "effect": detail}


# ---------- 工单处理（CS-010/013） ----------
class TicketResolveIn(BaseModel):
    reply: str = Field(min_length=1, max_length=2000)


@router.get("/admin/tickets")
def ticket_queue(status: str = "open", limit: int = Query(50, ge=1, le=200),
                 offset: int = Query(0, ge=0),
                 escalated_only: bool = False, mine: bool = False,
                 sort: Literal["id", "urgent"] = "id",
                 admin: User = Depends(require_role("support")), db: Session = Depends(get_db, scope="function")):
    """PAY-045 带分页：此前它接受 `offset` 然后忽略它——
    翻页的人会看到第一页无限重复，而且不知道自己在原地。
    **接受一个参数然后忽略它**，比拒绝它更糟。

    ESCA-051（150 号 spec）：每行带接手人、等了多久、超了多久、升到第几级；可只看已升级的、只看我接手的、
    按「最急」排（级别高的在前，同级等得久的在前）。默认排序不变。"""
    from app.modules.support.escalation import sla_view
    from app.modules.support.models import Ticket

    q = db.query(Ticket).filter(Ticket.status == status)
    if escalated_only:
        q = q.filter(Ticket.escalation_level > 0)
    if mine:
        q = q.filter(Ticket.assignee_id == admin.id)
    q = (q.order_by(Ticket.escalation_level.desc(), Ticket.created_at, Ticket.id) if sort == "urgent"
         else q.order_by(Ticket.id))
    rows = q.offset(offset).limit(limit).all()
    ids = {t.assignee_id for t in rows if t.assignee_id}
    names = {u.id: u.nickname for u in db.query(User).filter(User.id.in_(ids)).all()} if ids else {}
    now = utcnow()
    return [
        {"id": t.id, "user_id": t.user_id, "subject": t.subject, "body": t.body,
         "created_at": iso(t.created_at), "assignee_id": t.assignee_id,
         "assignee_nickname": names.get(t.assignee_id, "") if t.assignee_id else "",
         **sla_view(t, now)}
        for t in rows
    ]


@router.post("/admin/tickets/{ticket_id}/claim")
def claim_ticket(ticket_id: int, admin: User = Depends(require_role("support")),
                 db: Session = Depends(get_db, scope="function")):
    """ESCA-051 「我来处理」：接手后超时提醒只叫醒接手人。可以从别人手里接过来（主管指派、同事请假），
    审计里写明从谁手里接的。认领不重置计时。"""
    from app.modules.support.models import Ticket

    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.status != "open":
        raise not_found("工单不存在或已处理")
    prev = ticket.assignee_id
    ticket.assignee_id, ticket.claimed_at = admin.id, utcnow()
    record_audit(db, admin.id, "ticket_claim", "ticket", ticket.id,
                 f"接手工单（此前接手人：{'#' + str(prev) if prev else '无'}）")
    return {"id": ticket.id, "assignee_id": admin.id, "assignee_nickname": admin.nickname,
            "previous_assignee_id": prev}



@router.post("/admin/tickets/{ticket_id}/resolve")
def resolve_ticket(
    ticket_id: int, body: TicketResolveIn, admin: User = Depends(require_role("support")), db: Session = Depends(get_db, scope="function")
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
    q: str | None = None, admin: User = Depends(require_role("support", "compliance")), db: Session = Depends(get_db, scope="function"),
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


@router.get("/admin/users/{user_id}/ban-impact")
def ban_impact(user_id: int, admin: User = Depends(require_role("support", "compliance")), db: Session = Depends(get_db, scope="function")):
    """OPS-013 封禁前预览影响面（不产生副作用）。"""
    if not db.get(User, user_id):
        raise not_found("用户不存在")
    from . import service as admin_service

    return admin_service.ban_impact(db, user_id)


@router.post("/admin/users/{user_id}/ban")
def ban_user(user_id: int, admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function")):
    """OPS-013 封禁：影响面、对手方通知、挂单下架、审计——见 admin/service。"""
    from . import service as admin_service

    return admin_service.ban_user(db, admin.id, user_id)


@router.post("/admin/users/{user_id}/unban")
def unban_user(user_id: int, admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function")):
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
def create_category(body: CategoryIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
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
    admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function"),
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
def get_matching_config(admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    from app.modules.matching.service import get_weights

    return {"weights": get_weights(db)}


@router.put("/admin/matching-config")
def set_matching_config(
    body: WeightsIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")
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
def open_city(body: CityIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
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
    city_id: int, active: bool, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")
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
    # NTF-064 定时发送（151 号 spec）：不填就马上发（原有行为）
    scheduled_at: UtcDatetime | None = None


class AnnouncementPreviewIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(default="", max_length=2000)
    verified_only: bool = False


class AnnouncementCloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=200)


@router.post("/admin/announcements")
def broadcast_announcement(
    body: AnnouncementIn, admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")
):
    """OPS-009 平台公告：向全体（或已实名）活跃用户广播站内通知。

    NTF-064（151 号 spec）：每条公告留记录（谁、何时、发给谁、送达多少人）并进审计；可以定时；
    响应保留原有的 `delivered`，多了 `id`、`status`、`scheduled_at`。"""
    from . import announcements as ann_svc

    ann = ann_svc.create(db, admin.id, body.title, body.body, body.verified_only, body.scheduled_at)
    record_audit(db, admin.id, "announcement_schedule" if ann.status == "scheduled" else "announcement_send",
                 "announcement", ann.id,
                 f"「{ann.title[:60]}」{'仅已实名' if ann.verified_only else '全体'}，"
                 + (f"定时 {iso(ann.scheduled_at)}" if ann.status == "scheduled" else f"送达 {ann.delivered} 人"))
    return {"delivered": ann.delivered, "id": ann.id, "status": ann.status, "scheduled_at": iso(ann.scheduled_at)}


@router.post("/admin/announcements/preview")
def preview_announcement(body: AnnouncementPreviewIn, admin: User = Depends(require_role("ops")),
                         db: Session = Depends(get_db, scope="function")):
    """NTF-064 发之前先看：会送给多少人、多少人关了公告通知、用户看到的样子、要留意的地方。不发、不落库。"""
    from . import announcements as ann_svc

    return ann_svc.preview(db, body.title, body.body, body.verified_only)


@router.get("/admin/announcements")
def list_announcements(status: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                       admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    """NTF-064 公告记录：最新的在前；可按状态筛选（scheduled / sent / cancelled / revoked）。"""
    from . import announcements as ann_svc
    from .models import Announcement

    q = db.query(Announcement)
    if status:
        q = q.filter(Announcement.status == status)
    return [ann_svc.row(a) for a in q.order_by(Announcement.id.desc()).offset(offset).limit(limit).all()]


@router.post("/admin/announcements/{announcement_id}/cancel")
def cancel_announcement(announcement_id: int, body: AnnouncementCloseIn, admin: User = Depends(require_role("ops")),
                        db: Session = Depends(get_db, scope="function")):
    """NTF-064 取消还没发出的定时公告。"""
    from . import announcements as ann_svc

    ann = ann_svc.cancel(db, announcement_id, admin.id, body.reason.strip())
    record_audit(db, admin.id, "announcement_cancel", "announcement", ann.id, f"「{ann.title[:60]}」：{ann.close_reason}")
    return ann_svc.row(ann)


@router.post("/admin/announcements/{announcement_id}/revoke")
def revoke_announcement(announcement_id: int, body: AnnouncementCloseIn, admin: User = Depends(require_role("ops")),
                        db: Session = Depends(get_db, scope="function")):
    """NTF-064 撤回已发出的公告：已送达的通知改成「已撤回」并写明理由（理由必填）。推送收不回来。"""
    from . import announcements as ann_svc

    ann, n = ann_svc.revoke(db, announcement_id, admin.id, body.reason)
    record_audit(db, admin.id, "announcement_revoke", "announcement", ann.id,
                 f"「{ann.title[:60]}」改写 {n} 条通知：{ann.close_reason}")
    return {**ann_svc.row(ann), "notifications_updated": n}


# ---------- 平台收入结算（OPS-010） ----------
class SettleIn(BaseModel):
    amount_cents: int = Field(gt=0)
    memo: str = "平台收入结算"


@router.get("/admin/platform-finance")
def platform_finance(admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function")):
    """平台收入总览：累计佣金（实收）、已结算、可结算余额。"""
    from app.modules.wallet import service as wallet

    return wallet.platform_finance(db)


def _period_args(granularity: str, start: str, end: str) -> tuple[str, str, str]:
    """FIN-061 默认：北京时间最近 12 个月（月报）/ 最近 4 个季度（季报）。"""
    from app.modules.account.models import utcnow
    from app.modules.workbench.service import local

    now = local(utcnow())
    end = end or f"{now.year}-{now.month:02d}"
    if not start:
        back = 11 if granularity == "month" else 9
        y, m = now.year, now.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        start = f"{y}-{m:02d}"
    return granularity, start, end


PERIOD_PATTERN = r"^(\d{4}-(0[1-9]|1[0-2]))?$"   # 空串 = 用默认


@router.get("/admin/platform-finance/periods")
def platform_finance_periods(
    granularity: str = Query(default="month", pattern="^(month|quarter)$"),
    start: str = Query(default="", pattern=PERIOD_PATTERN),
    end: str = Query(default="", pattern=PERIOD_PATTERN),
    admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function"),
):
    """FIN-061 按期间的平台财务（144 号 spec）：本月佣金、本季结算——此前只有累计数。期间按北京时间自然月 / 季度。"""
    from app.modules.wallet import service as wallet

    out = wallet.platform_finance_periods(db, *_period_args(granularity, start, end))
    for r in out["periods"]:
        r["start"], r["end"] = iso(r["start"]), iso(r["end"])
    return out


@router.get("/admin/platform-finance/periods/export")
def export_platform_finance_periods(
    granularity: str = Query(default="month", pattern="^(month|quarter)$"),
    start: str = Query(default="", pattern=PERIOD_PATTERN),
    end: str = Query(default="", pattern=PERIOD_PATTERN),
    admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function"),
):
    """FIN-061 导出 CSV 给财务 / 记账代理：期间起止写成北京时间并在表头写明（TZ-068）；导出进审计。"""
    import csv
    import io

    from app.core.timefmt import EXPORT_TZ_LABEL, export_time
    from app.modules.wallet import service as wallet

    out = wallet.platform_finance_periods(db, *_period_args(granularity, start, end))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["期间", f"起（{EXPORT_TZ_LABEL}）", f"止（{EXPORT_TZ_LABEL}，不含）", "佣金收入（元）", "佣金笔数",
                "结算划出（元）", "补贴支出（元）", "其他调整（元）", "本期净额（元）", "期初余额（元）", "期末余额（元）", "自检"])
    for r in out["periods"]:
        w.writerow([r["period"], export_time(r["start"]), export_time(r["end"]), f"{r['fee_cents'] / 100:.2f}", r["fee_count"],
                    f"{r['settled_cents'] / 100:.2f}", f"{r['subsidy_cents'] / 100:.2f}", f"{r['other_cents'] / 100:.2f}",
                    f"{r['net_cents'] / 100:.2f}", f"{r['opening_cents'] / 100:.2f}", f"{r['closing_cents'] / 100:.2f}",
                    "平" if r["balanced"] else "不平"])
    first, last = out["periods"][0]["period"], out["periods"][-1]["period"]
    record_audit(db, admin.id, "export_platform_finance", "platform", None, f"{granularity} {first}~{last}")
    db.commit()
    return {"filename": f"platform-finance-{first}-{last}.csv", "rows": len(out["periods"]),
            "timezone": EXPORT_TZ_LABEL, "csv": buf.getvalue()}


@router.post("/admin/platform-finance/settle")
def settle_platform(
    body: SettleIn, admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function")
):
    """OPS-010 平台收入结算：把平台账户余额划出（模拟对公结算）。

    SEC-061c / PAY-042b（148 号 spec）：达到 `PLATFORM_SETTLE_DUAL_APPROVAL_CENTS` 的结算先记成「等第二位财务确认」，
    不动钱；另一位财务在「待确认的结算」里确认后才真的划出。小额照旧一步完成（响应不变）。"""
    from app.modules.wallet import service as wallet

    if body.amount_cents >= settings.PLATFORM_SETTLE_DUAL_APPROVAL_CENTS:
        bal = wallet.get_or_create(db, wallet.PLATFORM_USER_ID).available_cents
        if body.amount_cents <= 0 or body.amount_cents > bal:
            raise bad_request("结算金额超出平台可用余额", "insufficient_platform_balance")
        from .models import PlatformSettleRequest

        req = PlatformSettleRequest(amount_cents=body.amount_cents, memo=body.memo, requested_by=admin.id)
        db.add(req)
        db.flush()
        record_audit(db, admin.id, "platform_settle_request", "platform_settle", req.id,
                     f"发起结算 {body.amount_cents} 分：{body.memo}（等另一位财务确认）")
        return {"status": "awaiting_second", "request_id": req.id, "amount_cents": body.amount_cents,
                "balance_cents": bal,
                "message": f"达到 ¥{settings.PLATFORM_SETTLE_DUAL_APPROVAL_CENTS / 100:.2f} 的结算要另一位财务确认后才会划出"}
    result = wallet.settle_platform(db, body.amount_cents, body.memo)
    record_audit(db, admin.id, "platform_settle", "platform", None,
                 f"结算 {body.amount_cents} 分：{body.memo}")
    return result


def _settle_row(r) -> dict:
    return {"id": r.id, "amount_cents": r.amount_cents, "memo": r.memo, "requested_by": r.requested_by,
            "status": r.status, "decided_by": r.decided_by, "decision_reason": r.decision_reason,
            "created_at": iso(r.created_at), "decided_at": iso(r.decided_at),
            # SEC-061f（155 号 spec）：这一笔要超级管理员作第二人
            "needs_super_second": r.amount_cents >= settings.SUPER_SECOND_APPROVAL_CENTS}


@router.get("/admin/platform-finance/settle-requests")
def settle_requests(status: str = Query(default="awaiting_second", pattern="^(awaiting_second|settled|rejected)$"),
                    admin: User = Depends(require_role("finance")), db: Session = Depends(get_db, scope="function")):
    from .models import PlatformSettleRequest

    rows = (db.query(PlatformSettleRequest).filter(PlatformSettleRequest.status == status)
            .order_by(PlatformSettleRequest.id.desc()).limit(100).all())
    return [_settle_row(r) for r in rows]


class SettleDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(default="", max_length=200)


def _pending_settle(db: Session, request_id: int):
    from .models import PlatformSettleRequest

    req = (db.query(PlatformSettleRequest).filter(PlatformSettleRequest.id == request_id)
           .with_for_update().first())
    if req is None:
        raise not_found("没有这笔待确认的结算")
    if req.status != "awaiting_second":
        raise conflict("这笔结算已经处理过了", "settle_already_decided")
    return req


@router.post("/admin/platform-finance/settle-requests/{request_id}/approve")
def approve_settle(request_id: int, admin: User = Depends(require_role("finance")),
                   db: Session = Depends(get_db, scope="function")):
    """第二位财务确认：发起人自己不能确认（`same_approver`）；确认时再查一次余额，余额不够就不划。"""
    from app.modules.wallet import service as wallet

    req = _pending_settle(db, request_id)
    if req.requested_by == admin.id:
        raise bad_request(f"达到 ¥{settings.PLATFORM_SETTLE_DUAL_APPROVAL_CENTS / 100:.2f} 的结算要另一位财务确认："
                          "发起的就是你，请转交另一位财务", "same_approver")
    # SEC-061f（155 号 spec）：大额结算的第二人要超级管理员；第二人级别不低于发起人
    from app.core.admin_roles import check_second_approver

    check_second_approver(db.get(User, req.requested_by), admin, req.amount_cents)
    result = wallet.settle_platform(db, req.amount_cents, req.memo)
    req.status, req.decided_by, req.decided_at = "settled", admin.id, utcnow()
    record_audit(db, admin.id, "platform_settle", "platform_settle", req.id,
                 f"确认结算 {req.amount_cents} 分：{req.memo}（发起人 #{req.requested_by}）")
    return {**_settle_row(req), "balance_cents": result["balance_cents"]}


@router.post("/admin/platform-finance/settle-requests/{request_id}/reject")
def reject_settle(request_id: int, body: SettleDecisionIn, admin: User = Depends(require_role("finance")),
                  db: Session = Depends(get_db, scope="function")):
    """驳回或撤回（发起人自己也可以撤回）；不动钱。驳回别人发起的要写理由。"""
    req = _pending_settle(db, request_id)
    if req.requested_by != admin.id and len(body.reason.strip()) < 2:
        raise bad_request("驳回别人发起的结算要写明理由", "reason_required")
    req.status, req.decided_by, req.decided_at = "rejected", admin.id, utcnow()
    req.decision_reason = body.reason.strip() or "发起人撤回"
    record_audit(db, admin.id, "platform_settle_reject", "platform_settle", req.id,
                 f"驳回结算 {req.amount_cents} 分：{req.decision_reason}")
    return _settle_row(req)


# ---------- 对账 job（PAY-006/008） ----------
def _job_or_admin(
    x_job_token: str = Header(default=""),
    authorization: str = Header(default=""),
    db: Session = Depends(get_db, scope="function"),
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
    # SEC-061b 手动触发对账是财务的事（141 号 spec）；调度器走上面的令牌，不受影响
    from app.core.admin_roles import has_role, labels, roles_of

    if not has_role(user, "finance"):
        raise forbidden(f"这件事需要「财务」角色的管理员；你的角色是「{labels(sorted(roles_of(user)))}」", "admin_role_required")
    return user.id


@router.post("/admin/jobs/reconcile")
def run_reconcile(triggered_by: int = Depends(_job_or_admin),
                  db: Session = Depends(get_db, scope="function"),
                  __=Depends(job_slot("reconcile"), scope="function")):
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
def metrics(admin: User = Depends(require_role(*ANY)), db: Session = Depends(get_db, scope="function")):
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


# ---------- UMOD-020/021 上传审核队列 ----------
@router.get("/admin/uploads/pending")
def pending_uploads(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """UMOD-020 机审拿不准的图片队列。

    V62 把「这张图是谁传的」落了库，理由是「归属落库后处置才成为可能」。
    这个端点与下面的 resolve 就是那个处置——没有它们，那张表只是一张没人查的表。
    """
    from app.modules.files.models import UploadedFile

    rows = (
        db.query(UploadedFile)
        .filter(UploadedFile.moderation_status == "review")
        .order_by(UploadedFile.created_at).offset(offset).limit(limit).all()
    )
    return [
        {"name": r.name, "url": f"/api/v1/files/{r.name}", "owner_id": r.owner_id,
         "labels": r.moderation_labels, "content_type": r.content_type,
         "size_bytes": r.size_bytes, "created_at": iso(r.created_at)}
        for r in rows
    ]


class UploadVerdictIn(BaseModel):
    action: str = Field(pattern="^(pass|reject)$")
    reason: str = ""


@router.post("/admin/uploads/{name}/resolve")
def resolve_upload(
    name: str, body: UploadVerdictIn,
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """UMOD-021 审核员处置：通过，或**物理删除并告知上传者**。

    UMOD-022：悄悄删掉文件、让页面上变成裂图，是最差的一种处理。
    """
    from app.modules.files.models import UploadedFile
    from app.modules.notification.service import notify
    from app.vendors.registry import get_provider

    row = db.get(UploadedFile, name)
    if not row:
        raise not_found("上传记录不存在")
    if body.action == "pass":
        row.moderation_status = "pass"
        db.add(row)
        record_audit(db, admin.id, "upload_pass", "upload", None, f"{name}：{body.reason[:200]}")
        return {"name": name, "moderation_status": "pass"}

    provider = get_provider("storage")
    # UMOD-030 只删命名条目：别人上传过的同一份内容仍然有效
    # CONC-067 删文件是外部副作用：处置提交之后再删（处置回滚了就不删）
    from app.core.events import on_commit

    on_commit(db, "upload_reject_delete", lambda: getattr(provider, "delete", lambda _n: False)(name))
    removed = True
    row.moderation_status = "reject"
    db.add(row)
    notify(db, row.owner_id, "system", "一张图片已被移除",
           "你上传的一张图片经人工复核违反平台内容规范，已被移除。"
           "如果它是任务交付凭证，请重新上传合规的证据材料。")
    record_audit(db, admin.id, "upload_reject", "upload", None,
                 f"{name}：{body.reason[:200]}")
    return {"name": name, "moderation_status": "reject", "file_removed": removed}


# ---------- CERT 职业资质审核（51 号 spec）----------
#
# 改造前**管理后台里根本没有这个队列**：资质是用户自己 POST 进去的，
# 没有任何人看过任何一张证件。而受限类目的接单准入正是靠它。
class CertVerdictIn(BaseModel):
    approve: bool
    reason: str = ""


def _cert_row(db: Session, r) -> dict:
    """一条资质申请在运营侧长什么样。

    只有这一份实现：待核验列表与已核准列表用的是同一个（第二份实现必然抄漏）。
    """
    applicant = db.get(User, r.user_id)
    return {
        "id": r.id, "user_id": r.user_id, "name": r.name,
        "holder_name": r.holder_name, "cert_number": r.cert_number,
        "issuer": r.issuer,
        "expires_at": iso(r.expires_at),
        # CERT-010 证件影像走**鉴权**端点，不是匿名能力 URL
        "image_urls": [f"/api/v1/files/{n}/secure" for n in (r.images or [])],
        # 审核员要能一眼看到「证件姓名 vs 实名」是否一致
        "real_name": applicant.real_name if applicant else "",
        "name_matches": bool(applicant and r.holder_name == applicant.real_name),
        "status": r.status,
        "created_at": iso(r.created_at),
    }


def _certifications(db: Session, status: str, limit: int, offset: int = 0) -> list[dict]:
    from app.modules.account.models_cert import CertificationApplication

    rows = (db.query(CertificationApplication)
            .filter(CertificationApplication.status == status)
            .order_by(CertificationApplication.created_at)
            .offset(offset).limit(limit).all())
    return [_cert_row(db, r) for r in rows]


@router.get("/admin/certifications/pending")
def pending_certifications(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    return _certifications(db, "pending", limit, offset)


@router.get("/admin/certifications")
def list_certifications(
    status: str = Query("approved", pattern="^(pending|approved|rejected|revoked)$"),
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """CERT-031 按状态列资质（76 号 spec）。

    撤销（`revoke`）的对象是**已核准**的资质：证件过期、被发现造假、
    或被投诉后复核不通过。此前后台只能看到待核验的那些，
    于是「撤销」这个端点没有任何入口——一张已经核过的假证件撤不下来，
    持证人会继续接受限类目的单。
    """
    return _certifications(db, status, limit, offset)


@router.post("/admin/certifications/{application_id}/decide")
def decide_certification(
    application_id: int, body: CertVerdictIn,
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    from app.modules.account import cert_service
    from app.modules.account.models_cert import CertificationApplication

    row = db.get(CertificationApplication, application_id)
    if not row:
        raise not_found("资质申请不存在")
    row = cert_service.decide(db, row, admin, body.approve, body.reason)
    record_audit(db, admin.id, "certification_decide", "certification",
                 application_id, f"{'通过' if body.approve else '驳回'}：{body.reason}")
    return {"id": row.id, "status": row.status}


@router.post("/admin/certifications/{application_id}/revoke")
def revoke_certification(
    application_id: int, body: CertVerdictIn,
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    from app.modules.account import cert_service
    from app.modules.account.models_cert import CertificationApplication

    row = db.get(CertificationApplication, application_id)
    if not row:
        raise not_found("资质申请不存在")
    row = cert_service.revoke(db, row, admin, body.reason or "平台撤销")
    record_audit(db, admin.id, "certification_revoke", "certification",
                 application_id, body.reason)
    return {"id": row.id, "status": row.status}


# ---------- TEAM-031 团队企业信息核验（76 号 spec） ----------
#
# 探针：团队提交营业执照后 `verify_status = "pending"`，而**全仓没有任何端点**
# 能把它改成 `verified`——唯一那么写的地方是一条直接写库的测试。
# 于是 `can_invoice()` 在生产里永远返回那句拦截语：没有团队能开票，
# 也没有人能核过任何一个团队。**测试自己把状态改了，所以没有人发现
# 没有人能改它。**
class TeamVerifyIn(BaseModel):
    approve: bool
    reason: str = ""


@router.get("/admin/teams/pending")
def pending_teams(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    _: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """待核验的团队企业信息。

    执照影像走**鉴权**端点（`/files/{name}/secure`），不是匿名能力 URL——
    营业执照是企业敏感材料，与 CERT-010 的证件影像同一条（37 号 spec：
    上传文件的 URL 是能力，不是指纹）。
    """
    from app.modules.team.models import Team

    rows = (db.query(Team).filter(Team.verify_status == "pending")
            .order_by(Team.user_id).offset(offset).limit(limit).all())
    out = []
    for t in rows:
        owner = db.get(User, t.owner_id)
        images = [n for n in (t.license_images or "").split(",") if n]
        out.append({
            "team_id": t.user_id, "name": t.name, "owner_id": t.owner_id,
            "owner_nickname": owner.nickname if owner else "",
            "company_name": t.company_name, "tax_number": t.tax_number,
            "license_urls": [f"/api/v1/files/{n}/secure" for n in images],
            "created_at": iso(t.created_at),
        })
    return out


@router.post("/admin/teams/{team_id}/verify")
def verify_team(
    team_id: int, body: TeamVerifyIn,
    admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function"),
):
    """核过，或驳回**并写明要补什么**。

    驳回理由是强制的，而且必须**送到 owner 面前**：收不到理由，他只会
    把同一份材料再提交一遍（V92 那条「必须写」和「送到了」是两件事）。
    """
    from app.modules.notification.service import notify
    from app.modules.team.models import Team

    team = db.get(Team, team_id)
    if not team:
        raise not_found("团队不存在")
    if team.verify_status != "pending":
        raise bad_request("该团队没有待核验的企业信息", "not_pending")
    if not body.approve and not body.reason.strip():
        raise bad_request("驳回必须写明原因", "reason_required")

    team.verify_status = "verified" if body.approve else "rejected"
    team.verify_reason = body.reason
    db.add(team)
    if body.approve:
        notify(db, team.owner_id, "system", "团队企业信息已核验通过",
               f"「{team.name}」的企业信息已核验通过，现在可以开具发票。")
    else:
        notify(db, team.owner_id, "system", "团队企业信息未通过核验",
               f"「{team.name}」的企业信息未通过核验：{body.reason}。"
               f"请按说明补充材料后重新提交。")
    # 它决定这个团队能不能开票——有后果的动作要留痕
    record_audit(db, admin.id, "team_verify", "team", team_id,
                 f"{'通过' if body.approve else '驳回'}：{body.reason}")
    return {"team_id": team.user_id, "verify_status": team.verify_status,
            "verify_reason": team.verify_reason}


# ---------- QUEUE-010/011/012 人审队列概览与催办（78 号 spec） ----------
@router.get("/admin/queues")
def review_queues(_: User = Depends(require_role(*ANY)), db: Session = Depends(get_db, scope="function")):
    """每个人审队列：几件在等、最久等了多久、SLA 多长、超没超。

    三个地方共用这一份：催办 job、管理后台首屏、测试。
    各自去数库就会出现三份不一样的答案。
    """
    from .queues import snapshot

    rows = snapshot(db)
    return {
        "queues": rows,
        "total_pending": sum(r["pending"] for r in rows),
        "breached": [r["key"] for r in rows if r["breached"]],
    }


@router.post("/admin/jobs/remind-review-queues")
def run_remind_review_queues(_triggered_by: int = Depends(_job_or_admin),
                             db: Session = Depends(get_db, scope="function"),
                             __=Depends(job_slot("review_queue_reminders"), scope="function")):
    """QUEUE-011/012 队列积压催办。

    探针：四个队列里的东西推到 30 天前、跑一遍全部 job——
    **管理员和提交方一条通知都没有**。队列里躺着的东西不会主动发声，
    而运营是「想起来才去看」。

    发**一条汇总**而不是每个队列一条：四条相似的通知会让运营把整类关掉，
    而那一类里还有别的东西。
    """
    from app.modules.account.models import utcnow
    from app.modules.notification.service import notify

    from .models import QueueSlaNotice
    from .queues import QUEUES, snapshot

    now = utcnow()
    rows = {r["key"]: r for r in snapshot(db, now)}
    breached = [r for r in rows.values() if r["breached"]]

    digested = 0
    if breached:
        lines = "；".join(
            f"{r['label']} {r['pending']} 件（最久 {r['oldest_wait_hours']} 小时，"
            f"SLA {r['sla_hours']} 小时）"
            for r in breached
        )
        admins = [u.id for u in db.query(User).filter(User.is_admin.is_(True)).all()]
        for uid in admins:
            notify(db, uid, "system", "人审队列积压",
                   f"以下队列已超过 SLA：{lines}。请到管理后台处理。")
        digested = len(admins)

    # QUEUE-012 等的人也要收到一句话——沉默比慢更伤人
    told = 0
    for q in QUEUES:
        if not rows[q.key]["breached"] or not q.tells_submitter:
            continue        # 可疑活动复核不告知当事人：见 queues.py 里的理由
        sla = q.sla_hours()
        for item_id, at, submitter in q.pending(db):
            if submitter is None:
                continue
            if (now - at).total_seconds() < sla * 3600:
                continue
            key = str(item_id)
            seen = (db.query(QueueSlaNotice)
                    .filter(QueueSlaNotice.queue_key == q.key,
                            QueueSlaNotice.item_key == key).first())
            if seen:
                continue    # 每件只告知一次，否则每小时一条比不发更糟
            waited = int((now - at).total_seconds() // 3600)
            notify(db, submitter, "system", "你的申请仍在处理中",
                   f"你提交的「{q.label}」已等待 {waited} 小时，超过我们承诺的 "
                   f"{sla} 小时，我们已催办。给你带来的等待很抱歉。")
            db.add(QueueSlaNotice(queue_key=q.key, item_key=key))
            told += 1
    return {"breached": [r["key"] for r in breached], "admins_notified": digested,
            "submitters_told": told}


@router.post("/admin/jobs/send-scheduled-announcements")
def run_send_scheduled_announcements(_triggered_by: int = Depends(_job_or_admin),
                                     db: Session = Depends(get_db, scope="function"),
                                     __=Depends(job_slot("scheduled_announcements"), scope="function")):
    """NTF-064 定时公告到点发出（151 号 spec）：调度器每 5 分钟一次。"""
    from .announcements import send_due

    sent = send_due(db)
    return {"sent": sent}


@router.post("/admin/jobs/escalate-tickets")
def run_escalate_tickets(_triggered_by: int = Depends(_job_or_admin),
                         db: Session = Depends(get_db, scope="function"),
                         __=Depends(job_slot("ticket_escalations"), scope="function")):
    """ESCA-051 工单超时逐级升级（150 号 spec）：调度器每小时跑一次；每级只叫一次人。"""
    from app.modules.support.escalation import escalate_overdue

    return escalate_overdue(db)


# ------------------------------------------------------------------ SEC-061b 管理员与角色（141 号 spec）
class AdminRolesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: list[str] = Field(min_length=1, max_length=6)


def _admin_row(u: User) -> dict:
    from app.core.admin_roles import roles_of

    return {"user_id": u.id, "nickname": u.nickname, "roles": sorted(roles_of(u)),
            "unclassified": not [r for r in (u.admin_roles or []) if r]}


@router.get("/admin/roles")
def admin_role_catalog(user: User = Depends(require_role(*ANY))):
    """角色说明与我自己的角色：后台按这个决定显示哪些板块（拦在服务端，显示只是不让人白点）。"""
    from app.core.admin_roles import ROLES, roles_of

    return {"roles": [{"key": k, "label": v.split("：")[0], "scope": v.split("：", 1)[1]} for k, v in ROLES.items()],
            "mine": sorted(roles_of(user))}


@router.get("/admin/admins")
def list_admins(_: User = Depends(require_role("super")), db: Session = Depends(get_db, scope="function")):
    rows = [_admin_row(u) for u in db.query(User).filter(User.is_admin.is_(True), User.is_deleted.is_(False))
            .order_by(User.id)]
    return {"admins": rows, "unclassified": sum(1 for r in rows if r["unclassified"])}


@router.put("/admin/admins/{user_id}/roles")
def set_admin_roles(user_id: int, body: AdminRolesIn, admin: User = Depends(require_role("super")),
                    db: Session = Depends(get_db, scope="function")):
    """只有超级管理员能分配；至少留一位超级管理员；每次都进审计。"""
    from app.core.admin_roles import ROLES, roles_of

    target = db.get(User, user_id)
    if target is None or not target.is_admin or target.is_deleted:
        raise not_found("这个用户不是管理员：管理员身份由运维开通，这里只分配角色", "admin_target_not_admin")
    unknown = sorted(set(body.roles) - set(ROLES))
    if unknown:
        raise bad_request(f"不认识的角色：{'、'.join(unknown)}；可选的是 {'、'.join(ROLES)}", "admin_role_unknown")
    new = sorted(set(body.roles))
    others_super = [u for u in db.query(User).filter(User.is_admin.is_(True), User.is_deleted.is_(False), User.id != target.id)
                    if "super" in roles_of(u)]
    if "super" not in new and not others_super:
        raise conflict("至少要留一位超级管理员：否则以后没人能再分配角色。先给另一位管理员加上「超级管理员」",
                       "admin_last_super")
    before = sorted(roles_of(target))
    target.admin_roles = new
    record_audit(db, admin.id, "set_admin_roles", "user", target.id, f"{before} -> {new}")
    db.commit()
    return _admin_row(target)

