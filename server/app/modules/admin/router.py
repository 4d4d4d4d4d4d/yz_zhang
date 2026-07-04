"""管理后台 API（12.E）：用户管理、举报处置队列、平台指标看板。"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_admin
from app.core.errors import bad_request, not_found
from app.modules.account.models import User
from app.modules.content.models import Content
from app.modules.contract.models import Contract
from app.modules.dispute.models import Dispute
from app.modules.task.models import Task

from .models import Report

router = APIRouter(tags=["admin"])


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


@router.post("/admin/users/{user_id}/ban")
def ban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    if user.is_admin:
        raise bad_request("不能封禁管理员", "cannot_ban_admin")
    user.is_banned = True
    db.add(user)
    return {"id": user.id, "is_banned": True}


@router.post("/admin/users/{user_id}/unban")
def unban_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    user.is_banned = False
    db.add(user)
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


# ---------- 对账 job（PAY-006） ----------
@router.post("/admin/jobs/reconcile")
def run_reconcile(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.modules.risk.service import reconcile

    return reconcile(db)


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
    fee_income = (
        db.query(Contract)
        .filter(Contract.released_cents > 0)
        .with_entities(func.coalesce(func.sum(Contract.released_cents * Contract.fee_bps / 10000), 0))
        .scalar()
    )
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
