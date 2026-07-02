from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_verified
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.events import publish
from app.core.geoutil import haversine_m
from app.modules.account import service as credit
from app.modules.account.models import User, utcnow
from app.modules.contract import service as contract_service
from app.modules.contract.models import Contract
from app.modules.matching import service as matching

from . import service
from .models import TASK_TYPES, Application, ProgressLog, Review, Task

router = APIRouter(tags=["task"])


# ---------- schemas ----------
class TaskIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = ""
    category: str = Field(min_length=1, max_length=50)
    task_type: str = "service"
    required_skills: list[str] = []
    budget_cents: int = 0
    pricing: str = "fixed"
    is_remote: bool = False
    city: str = ""
    lat: float | None = None
    lng: float | None = None
    address_hint: str = ""
    address_exact: str = ""
    deadline: datetime | None = None
    publish_now: bool = True


class ApplyIn(BaseModel):
    bid_cents: int = 0
    message: str = ""


class ProgressIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CheckinIn(BaseModel):
    lat: float
    lng: float


class RejectIn(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


class ReviewIn(BaseModel):
    stars: int = Field(ge=1, le=5)
    tags: list[str] = []
    comment: str = ""


def dump_task(task: Task, viewer: User | None = None) -> dict:
    is_party = viewer and viewer.id in (task.creator_id, task.executor_id)
    return {
        "id": task.id,
        "creator_id": task.creator_id,
        "executor_id": task.executor_id,
        "parent_id": task.parent_id,
        "depends_on": task.depends_on,
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "task_type": task.task_type,
        "required_skills": task.required_skills,
        "budget_cents": task.budget_cents,
        "pricing": task.pricing,
        "is_remote": task.is_remote,
        "city": task.city,
        "lat": task.lat,
        "lng": task.lng,
        "address_hint": task.address_hint,
        # GEO-004 位置脱敏：精确地址仅成交双方可见
        "address_exact": task.address_exact if is_party else "",
        "status": task.status,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "reject_count": task.reject_count,
        "created_at": task.created_at.isoformat(),
    }


def _get_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    return task


# ---------- 发布（TASK-001/004/005）----------
@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.task_type not in TASK_TYPES:
        raise bad_request("非法任务类型", "invalid_type")
    task = Task(creator_id=user.id, **body.model_dump(exclude={"publish_now"}))
    db.add(task)
    db.flush()
    if body.publish_now:
        service.validate_publishable(task)
        service.transition(db, task, "published")
    return dump_task(task, user)


@router.post("/tasks/{task_id}/publish")
def publish_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    service.validate_publishable(task)
    service.transition(db, task, "published")
    return dump_task(task, user)


# ---------- 广场 / 搜索 / LBS（TASK-040/041, GEO-010/011）----------
@router.get("/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    q: str | None = None,
    category: str | None = None,
    task_type: str | None = None,
    city: str | None = None,
    status: str = "published",
    lat: float | None = None,
    lng: float | None = None,
    max_km: float = Query(default=0, ge=0),
    limit: int = Query(default=20, le=100),
):
    query = db.query(Task).filter(Task.status == status)
    if q:
        query = query.filter(Task.title.contains(q) | Task.description.contains(q))
    if category:
        query = query.filter(Task.category == category)
    if task_type:
        query = query.filter(Task.task_type == task_type)
    if city:
        query = query.filter(Task.city == city)
    rows = query.order_by(Task.id.desc()).limit(500).all()
    items = []
    for task in rows:
        distance_m = None
        if lat is not None and lng is not None and task.lat is not None:
            distance_m = round(haversine_m(lat, lng, task.lat, task.lng))
            if max_km and distance_m > max_km * 1000:
                continue
        item = dump_task(task)
        item["distance_m"] = distance_m
        items.append(item)
    if lat is not None:
        items.sort(key=lambda x: (x["distance_m"] is None, x["distance_m"] or 0))
    return items[:limit]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return dump_task(_get_task(db, task_id), user)


# ---------- 报名与推荐（MATCH-001/002）----------
@router.post("/tasks/{task_id}/applications", status_code=201)
def apply(
    task_id: int,
    body: ApplyIn,
    user: User = Depends(require_verified),
    db: Session = Depends(get_db),
):
    task = _get_task(db, task_id)
    if task.status != "published":
        raise conflict("任务不在招募中", "not_recruiting")
    if task.creator_id == user.id:
        raise bad_request("不能报名自己发布的任务", "self_apply")
    dup = (
        db.query(Application)
        .filter(Application.task_id == task_id, Application.applicant_id == user.id)
        .first()
    )
    if dup:
        raise conflict("已报名过该任务", "already_applied")
    app_row = Application(
        task_id=task_id,
        applicant_id=user.id,
        bid_cents=body.bid_cents or task.budget_cents,
        message=body.message,
    )
    db.add(app_row)
    db.flush()
    return {"id": app_row.id, "status": app_row.status}


@router.get("/tasks/{task_id}/applications")
def list_applications(
    task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    rows = db.query(Application).filter(Application.task_id == task_id).all()
    out = []
    for r in rows:
        applicant = db.get(User, r.applicant_id)
        out.append(
            {
                "id": r.id,
                "applicant_id": r.applicant_id,
                "nickname": applicant.nickname if applicant else "",
                "credit_score": applicant.credit_score if applicant else 0,
                "rating_avg": applicant.rating_avg if applicant else 0,
                "bid_cents": r.bid_cents,
                "message": r.message,
                "status": r.status,
            }
        )
    return out


@router.get("/tasks/{task_id}/recommendations")
def recommendations(
    task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    return matching.recommend(db, task)


@router.post("/applications/{application_id}/accept")
def accept_application(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """TASK-020 双方确认成交 → 生成合约（SC-001），任务 → matched。"""
    app_row = db.get(Application, application_id)
    if not app_row:
        raise not_found("报名不存在")
    task = _get_task(db, app_row.task_id)
    if task.creator_id != user.id:
        raise forbidden()
    if task.status != "published":
        raise conflict("任务不在招募中", "not_recruiting")
    app_row.status = "accepted"
    task.executor_id = app_row.applicant_id
    db.add_all([app_row, task])
    contract = contract_service.generate(db, task, app_row.applicant_id, app_row.bid_cents)
    service.transition(db, task, "matched", {"executor_id": app_row.applicant_id})
    db.query(Application).filter(
        Application.task_id == task.id, Application.id != app_row.id
    ).update({"status": "rejected"})
    return {"contract_id": contract.id, "task": dump_task(task, user)}


# ---------- 执行留痕（TASK-022, GEO-020）----------
@router.post("/tasks/{task_id}/progress", status_code=201)
def add_progress(
    task_id: int, body: ProgressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    if task.status not in ("in_progress", "pending_acceptance"):
        raise conflict("任务不在执行中", "not_in_progress")
    log = ProgressLog(task_id=task_id, user_id=user.id, kind="note", content=body.content)
    db.add(log)
    return {"ok": True}


@router.post("/tasks/{task_id}/checkin", status_code=201)
def checkin(
    task_id: int, body: CheckinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if user.id != task.executor_id:
        raise forbidden("仅执行者可打卡")
    if task.status != "in_progress":
        raise conflict("任务不在执行中", "not_in_progress")
    if task.is_remote or task.lat is None:
        raise bad_request("线上任务无需到场打卡", "no_checkin_needed")
    distance = haversine_m(task.lat, task.lng, body.lat, body.lng)
    if distance > settings.CHECKIN_RADIUS_M:
        raise bad_request(f"距任务地点 {distance:.0f} 米，超出打卡范围", "too_far")
    db.add(
        ProgressLog(
            task_id=task_id, user_id=user.id, kind="checkin",
            content=f"到场打卡（距离 {distance:.0f} 米）", lat=body.lat, lng=body.lng,
        )
    )
    return {"ok": True, "distance_m": round(distance)}


@router.get("/tasks/{task_id}/progress")
def list_progress(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id) and not user.is_admin:
        raise forbidden()
    rows = db.query(ProgressLog).filter(ProgressLog.task_id == task_id).order_by(ProgressLog.id).all()
    return [
        {"id": r.id, "user_id": r.user_id, "kind": r.kind, "content": r.content,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


# ---------- 交付与验收（TASK-030/031/033）----------
@router.post("/tasks/{task_id}/deliver")
def deliver(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if user.id != task.executor_id:
        raise forbidden("仅执行者可提交验收")
    task.delivered_at = utcnow()
    db.add(ProgressLog(task_id=task_id, user_id=user.id, kind="delivery", content="提交验收"))
    service.transition(db, task, "pending_acceptance")
    return dump_task(task, user)


@router.post("/tasks/{task_id}/accept-delivery")
def accept_delivery(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    _complete_task(db, task)
    return dump_task(task, user)


@router.post("/tasks/{task_id}/reject-delivery")
def reject_delivery(
    task_id: int, body: RejectIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    task.reject_count += 1
    db.add(ProgressLog(task_id=task_id, user_id=user.id, kind="note", content=f"验收驳回：{body.reason}"))
    service.transition(db, task, "in_progress")
    return dump_task(task, user)


def _complete_task(db: Session, task: Task) -> None:
    """验收通过：放款（SC-005）→ 完成 → 信用更新 → task.completed 事件（经验入库等）。"""
    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    if contract:
        contract_service.release(db, contract)
    task.completed_at = utcnow()
    service.transition(db, task, "completed")
    if task.executor_id:
        credit.record_task_completed(db, task.executor_id)


@router.post("/tasks/jobs/auto-accept")
def run_auto_accept(db: Session = Depends(get_db)):
    """TASK-031 超时自动验收（生产为定时任务，这里同时暴露为可调用 job）。"""
    cutoff = utcnow() - timedelta(days=settings.AUTO_ACCEPT_DAYS)
    rows = (
        db.query(Task)
        .filter(Task.status == "pending_acceptance", Task.delivered_at <= cutoff)
        .all()
    )
    for task in rows:
        _complete_task(db, task)
    return {"auto_accepted": len(rows)}


# ---------- 取消（TASK-026 / SC-006）----------
@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    if task.status == "pending_acceptance":
        raise conflict("待验收阶段不可单方取消，请验收或发起纠纷", "not_cancellable")
    result = {}
    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    if contract and contract.status not in ("cancelled", "refunded", "released", "split"):
        result = contract_service.cancel(db, contract, user.id)
        # 托管后执行者违约取消 → 信用惩罚（CRED-004）
        if result.get("cancelled_by") == "executor":
            credit.adjust_credit(db, user.id, credit.CREDIT_CANCEL_PENALTY)
    service.transition(db, task, "cancelled")
    return {"task": dump_task(task, user), **result}


# ---------- 双向评价（TASK-034 / CRED-002）----------
@router.post("/tasks/{task_id}/reviews", status_code=201)
def create_review(
    task_id: int, body: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = _get_task(db, task_id)
    if task.status != "completed":
        raise conflict("任务完成后才能评价", "not_completed")
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    target_id = task.executor_id if user.id == task.creator_id else task.creator_id
    dup = db.query(Review).filter(Review.task_id == task_id, Review.reviewer_id == user.id).first()
    if dup:
        raise conflict("已评价过", "already_reviewed")
    review = Review(
        task_id=task_id, reviewer_id=user.id, target_id=target_id,
        stars=body.stars, tags=body.tags, comment=body.comment,
    )
    db.add(review)
    credit.record_review(db, target_id, body.stars)
    publish(db, "review.submitted", {"task_id": task_id, "target_id": target_id, "stars": body.stars})
    return {"ok": True}


@router.get("/tasks/{task_id}/reviews")
def list_reviews(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """盲评（CRED-002）：双方都评完前，当事人只能看到自己提交的评价。"""
    task = _get_task(db, task_id)
    rows = db.query(Review).filter(Review.task_id == task_id).all()
    both_done = len(rows) >= 2
    out = []
    for r in rows:
        if user.id in (task.creator_id, task.executor_id) and not both_done and r.reviewer_id != user.id:
            continue
        out.append(
            {"reviewer_id": r.reviewer_id, "target_id": r.target_id, "stars": r.stars,
             "tags": r.tags, "comment": r.comment}
        )
    return out
