from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth, require_verified
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
    deposit_cents: int = 0
    is_remote: bool = False
    city: str = ""
    lat: float | None = None
    lng: float | None = None
    address_hint: str = ""
    address_exact: str = ""
    deadline: datetime | None = None
    visibility: str = "public"
    circle_id: int | None = None
    recurrence: str = "none"
    people_needed: int = Field(default=1, ge=1, le=50)
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
        "deposit_cents": task.deposit_cents,
        "is_remote": task.is_remote,
        "city": task.city,
        "lat": task.lat,
        "lng": task.lng,
        "address_hint": task.address_hint,
        # GEO-004 位置脱敏：精确地址仅成交双方可见
        "address_exact": task.address_exact if is_party else "",
        "visibility": task.visibility,
        "circle_id": task.circle_id,
        "recurrence": task.recurrence,
        "recurred_from_id": task.recurred_from_id,
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
    if body.visibility not in ("public", "circle"):
        raise bad_request("非法可见范围", "invalid_visibility")
    if body.recurrence not in ("none", "weekly", "monthly"):
        raise bad_request("非法周期设置", "invalid_recurrence")
    service.validate_category(db, body.category)  # OPS-004 类目启停校验
    if body.visibility == "circle":
        # TASK-008/CIR-005 圈层定向任务：发布者必须是活跃成员
        from app.modules.circle.router import active_member

        if not body.circle_id or not active_member(db, body.circle_id, user.id):
            raise forbidden("需先加入该圈层", "not_circle_member")
    task = Task(creator_id=user.id, **body.model_dump(exclude={"publish_now"}))
    db.add(task)
    db.flush()
    # TASK-007 多人任务：母任务为容器（不进广场），生成 N 个名额子任务分别招募
    if body.people_needed > 1:
        service.validate_publishable(task, db)
        per_slot = body.budget_cents // body.people_needed
        if per_slot <= 0:
            raise bad_request("预算不足以拆分名额", "budget_too_small")
        # 预算守恒：整除余数并入末位名额，保证 Σ名额预算 == 母任务预算
        remainder = body.budget_cents - per_slot * body.people_needed
        slots = []
        for i in range(body.people_needed):
            slot_budget = per_slot + (remainder if i == body.people_needed - 1 else 0)
            slot = Task(
                creator_id=user.id, parent_id=task.id,
                title=f"{task.title} · 名额{i + 1}/{body.people_needed}",
                description=task.description, category=task.category,
                task_type=task.task_type, required_skills=task.required_skills,
                budget_cents=slot_budget, pricing=task.pricing, deposit_cents=task.deposit_cents,
                is_remote=task.is_remote, city=task.city, lat=task.lat, lng=task.lng,
                address_hint=task.address_hint, address_exact=task.address_exact,
                visibility=task.visibility, circle_id=task.circle_id,
            )
            db.add(slot)
            slots.append(slot)
        db.flush()
        for slot in slots:
            service.transition(db, slot, "published")
        out = dump_task(task, user)
        out["slots"] = [dump_task(s, user) for s in slots]
        return out
    if body.publish_now:
        service.validate_publishable(task, db)
        service.transition(db, task, "published")
    return dump_task(task, user)


@router.post("/tasks/{task_id}/publish")
def publish_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    service.validate_publishable(task, db)
    service.transition(db, task, "published")
    return dump_task(task, user)


class TaskEditIn(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = None
    budget_cents: int | None = Field(default=None, gt=0)
    required_skills: list[str] | None = None
    address_hint: str | None = None
    address_exact: str | None = None
    deadline: datetime | None = None


# 已发布任务上「实质性」字段（影响报名者决策），有人报名后受保护（TASK-014 防调包）
_MATERIAL_FIELDS = {"budget_cents", "required_skills"}


@router.patch("/tasks/{task_id}")
def edit_task(
    task_id: int, body: TaskEditIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """TASK-014 任务编辑 + 防调包（bait-and-switch）保护。

    draft 阶段可自由改；已发布后一旦有人报名，实质性条款（预算、技能要求）
    受保护：预算只可上调不可下调，技能要求锁定——防止「高价招人、低价成交」；
    非实质字段（标题/描述/地址提示）始终可改。实质变更会通知已报名者。
    """
    task = _get_task(db, task_id)
    if task.creator_id != user.id:
        raise forbidden()
    if task.status not in ("draft", "published"):
        raise conflict("任务已进入执行阶段，不可编辑（请走合约变更单）", "not_editable")
    changes = body.model_dump(exclude_none=True)
    if not changes:
        return dump_task(task, user)

    has_applicants = db.query(Application).filter(
        Application.task_id == task_id, Application.status == "pending"
    ).count() > 0
    protected = task.status == "published" and has_applicants
    material_changed = False

    for field, value in changes.items():
        if field == "budget_cents" and value != task.budget_cents:
            if protected and value < task.budget_cents:
                raise conflict("已有报名者，预算不可下调（防调包），只能上调", "budget_locked")
            material_changed = material_changed or field in _MATERIAL_FIELDS
        if field == "required_skills" and value != task.required_skills:
            if protected:
                raise conflict("已有报名者，技能要求已锁定", "skills_locked")
            material_changed = material_changed or field in _MATERIAL_FIELDS
        setattr(task, field, value)
    db.add(task)

    # 实质性上调 → 通知已报名者，可重新评估（业界惯例：透明变更）
    if protected and material_changed:
        from app.modules.notification.service import notify

        apps = db.query(Application).filter(
            Application.task_id == task_id, Application.status == "pending"
        ).all()
        for a in apps:
            notify(db, a.applicant_id, "task", "报名的任务有更新",
                   f"《{task.title}》发布方上调了预算至 {task.budget_cents / 100:.2f} 元，请留意。")
    return dump_task(task, user)


@router.get("/tasks/mine")
def my_tasks(
    role: str = Query(default="all", pattern="^(all|posted|working)$"),
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """TASK-016 我的任务：我发布的（posted）/ 我执行的（working）/ 全部（all），可按状态筛选。

    广场只展示 published+public，用户无法在其中看到自己的草稿/执行中/已完成任务，
    此端点补齐个人任务中心（订单页）能力。含多人任务的名额子任务。
    """
    from sqlalchemy import or_

    query = db.query(Task)
    if role == "posted":
        query = query.filter(Task.creator_id == user.id)
    elif role == "working":
        query = query.filter(Task.executor_id == user.id)
    else:
        query = query.filter(or_(Task.creator_id == user.id, Task.executor_id == user.id))
    if status:
        query = query.filter(Task.status == status)
    rows = query.order_by(Task.id.desc()).offset(offset).limit(limit).all()
    return [dump_task(t, user) for t in rows]


@router.get("/users/me/applications")
def my_applications(
    status: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """MATCH-010 我的报名：列出本人投出的报名及所报任务的当前状态。

    /tasks/mine?role=working 只含已成交单，等待选人的报名无处可查——此端点补齐。
    """
    query = db.query(Application).filter(Application.applicant_id == user.id)
    if status:
        query = query.filter(Application.status == status)
    rows = query.order_by(Application.id.desc()).offset(offset).limit(limit).all()
    task_ids = [a.task_id for a in rows]
    tasks = {t.id: t for t in db.query(Task).filter(Task.id.in_(task_ids))} if task_ids else {}
    out = []
    for a in rows:
        t = tasks.get(a.task_id)
        out.append({
            "application_id": a.id, "task_id": a.task_id, "status": a.status,
            "bid_cents": a.bid_cents, "message": a.message,
            "created_at": a.created_at.isoformat(),
            "task_title": t.title if t else None,
            "task_status": t.status if t else None,
            "task_budget_cents": t.budget_cents if t else None,
        })
    return out


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """OPS-004 类目列表（公开，发布表单数据源）。"""
    from .models import Category

    rows = db.query(Category).filter(Category.active.is_(True)).order_by(Category.id).all()
    return [{"id": c.id, "name": c.name, "required_cert": c.required_cert} for c in rows]


@router.get("/task-templates")
def task_templates(category: str, db: Session = Depends(get_db)):
    """TASK-003 任务模板库：模板 + 同类参考价一并返回。"""
    from app.modules.knowledge import service as kb

    template = service.TASK_TEMPLATES.get(category)
    if not template:
        raise not_found("该类目暂无模板")
    return {"category": category, **template, "price_reference": kb.price_reference(db, category)}


@router.get("/cities")
def list_cities(db: Session = Depends(get_db)):
    """GEO-030 已开通城市列表。"""
    from .models import City

    rows = db.query(City).filter(City.active.is_(True)).order_by(City.id).all()
    return [{"id": c.id, "name": c.name} for c in rows]


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
    offset: int = Query(default=0, ge=0),
):
    # 公开广场不展示圈层定向任务（TASK-008）
    query = db.query(Task).filter(Task.status == status, Task.visibility == "public")
    if q:
        query = query.filter(Task.title.contains(q) | Task.description.contains(q))
    if category:
        query = query.filter(Task.category == category)
    if task_type:
        query = query.filter(Task.task_type == task_type)
    if city:
        query = query.filter(Task.city == city)
    query = query.order_by(Task.id.desc())
    # 非地理浏览：DB 层 offset/limit 分页，可翻至任意页且不拉全表（TASK-003）
    if lat is None or lng is None:
        rows = query.offset(offset).limit(limit).all()
        return [dump_task(t) | {"distance_m": None} for t in rows]
    # 地理检索：取候选窗口按距离过滤+排序后再分页（规模化替换为空间索引）
    rows = query.limit(500).all()
    items = []
    for task in rows:
        distance_m = None
        if task.lat is not None:
            distance_m = round(haversine_m(lat, lng, task.lat, task.lng))
            if max_km and distance_m > max_km * 1000:
                continue
        item = dump_task(task)
        item["distance_m"] = distance_m
        items.append(item)
    items.sort(key=lambda x: (x["distance_m"] is None, x["distance_m"] or 0))
    return items[offset:offset + limit]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """TASK-017 任务详情附「我与此任务的关系」上下文：是否已报名/收藏，
    发布者可见报名数——避免用户重复报名后才被 409 拒绝的糟糕体验。"""
    from sqlalchemy import func

    task = _get_task(db, task_id)
    out = dump_task(task, user)
    from .models import Bookmark

    my_app = (
        db.query(Application)
        .filter(Application.task_id == task_id, Application.applicant_id == user.id)
        .order_by(Application.id.desc()).first()
    )
    out["my_application_status"] = my_app.status if my_app else None
    out["bookmarked"] = db.query(Bookmark).filter(
        Bookmark.user_id == user.id, Bookmark.task_id == task_id
    ).first() is not None
    if task.creator_id == user.id:
        out["applications_count"] = (
            db.query(func.count(Application.id))
            .filter(Application.task_id == task_id, Application.status == "pending")
            .scalar()
        )
    return out


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
    service.check_category_qualification(db, task, user)  # ACC-022 受限类目准入
    service.check_executor_capacity(db, user.id)  # TASK-011 并发接单上限
    from app.modules.account.service import is_blocked_between

    if is_blocked_between(db, user.id, task.creator_id):  # ACC-033
        raise forbidden("无法报名该任务", "blocked")
    dup = (
        db.query(Application)
        .filter(Application.task_id == task_id, Application.applicant_id == user.id,
                Application.status != "withdrawn")  # TASK-012 撤回后允许重新报名
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
    if app_row.status != "pending":  # TASK-012 已撤回/已拒的报名不可成交（防替人签约）
        raise conflict("该报名已撤回或已处理", "application_closed")
    service.check_executor_capacity(db, app_row.applicant_id)  # TASK-011 成交时复核在途上限
    app_row.status = "accepted"
    task.executor_id = app_row.applicant_id
    db.add_all([app_row, task])
    contract = contract_service.generate(db, task, app_row.applicant_id, app_row.bid_cents)
    service.transition(db, task, "matched", {"executor_id": app_row.applicant_id})
    db.query(Application).filter(
        Application.task_id == task.id, Application.id != app_row.id
    ).update({"status": "rejected"})
    return {"contract_id": contract.id, "task": dump_task(task, user)}


# ---------- TASK-013 收藏 ----------
@router.post("/tasks/{task_id}/bookmark", status_code=201)
def add_bookmark(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Bookmark

    _get_task(db, task_id)  # 任务需存在
    dup = db.query(Bookmark).filter(
        Bookmark.user_id == user.id, Bookmark.task_id == task_id
    ).first()
    if dup:
        return {"ok": True, "already": True}  # 幂等
    db.add(Bookmark(user_id=user.id, task_id=task_id))
    return {"ok": True}


@router.delete("/tasks/{task_id}/bookmark")
def remove_bookmark(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Bookmark

    db.query(Bookmark).filter(
        Bookmark.user_id == user.id, Bookmark.task_id == task_id
    ).delete()
    return {"ok": True}


@router.get("/users/me/bookmarks")
def my_bookmarks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from .models import Bookmark

    rows = (
        db.query(Bookmark).filter(Bookmark.user_id == user.id)
        .order_by(Bookmark.id.desc()).limit(100).all()
    )
    ids = [r.task_id for r in rows]
    tasks = {t.id: t for t in db.query(Task).filter(Task.id.in_(ids))} if ids else {}
    return [dump_task(tasks[i], user) for i in ids if i in tasks]


@router.post("/applications/{application_id}/withdraw")
def withdraw_application(
    application_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """TASK-012 报名撤回（业界标配）：仅本人、仅 pending 可撤；撤回后可重新报名。"""
    app_row = db.get(Application, application_id)
    if not app_row:
        raise not_found("报名不存在")
    if app_row.applicant_id != user.id:
        raise forbidden()
    if app_row.status != "pending":
        raise conflict("该报名已处理，不可撤回", "application_closed")
    app_row.status = "withdrawn"
    db.add(app_row)
    return {"id": app_row.id, "status": "withdrawn"}


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


# ---------- GEO 安全件（GEO-021/023/024）----------
@router.post("/tasks/{task_id}/trip-share")
def toggle_trip_share(
    task_id: int, enabled: bool, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """GEO-021 行程共享开关（执行者，仅执行中）。"""
    task = _get_task(db, task_id)
    if user.id != task.executor_id:
        raise forbidden("仅执行者可设置行程共享")
    if task.status != "in_progress":
        raise conflict("任务不在执行中", "not_in_progress")
    task.trip_share_enabled = enabled
    db.add(task)
    return {"trip_share_enabled": enabled}


@router.get("/tasks/{task_id}/trip")
def get_trip(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """发布者查看执行者最近打卡位置（需执行者开启共享，任务结束即失效）。"""
    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    if not task.trip_share_enabled or task.status != "in_progress":
        raise forbidden("行程共享未开启或任务已结束", "trip_share_disabled")
    last = (
        db.query(ProgressLog)
        .filter(ProgressLog.task_id == task_id, ProgressLog.kind == "checkin",
                ProgressLog.lat.isnot(None))
        .order_by(ProgressLog.id.desc())
        .first()
    )
    if not last:
        return {"lat": None, "lng": None, "at": None}
    return {"lat": last.lat, "lng": last.lng, "at": last.created_at.isoformat()}


@router.post("/tasks/{task_id}/sos", status_code=201)
def sos(task_id: int, body: CheckinIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """GEO-023 紧急求助：留痕 + 通知对方与平台（生产联动 110/紧急联系人）。"""
    task = _get_task(db, task_id)
    if user.id not in (task.creator_id, task.executor_id):
        raise forbidden()
    db.add(ProgressLog(task_id=task_id, user_id=user.id, kind="sos",
                       content="紧急求助", lat=body.lat, lng=body.lng))
    from app.modules.notification.service import notify

    other = task.executor_id if user.id == task.creator_id else task.creator_id
    if other:
        notify(db, other, "system", "对方发出紧急求助",
               f"任务《{task.title}》的另一方发出紧急求助，请立即联系确认安全")
    return {"ok": True, "guidance": "已通知平台与任务对方；如遇危险请立即拨打 110"}


@router.post("/tasks/jobs/purge-locations")
def purge_locations(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """GEO-024 位置保留策略：已结束任务超过 30 天，清除打卡精确坐标。"""
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=30)
    closed_ids = [
        t.id for t in db.query(Task)
        .filter(Task.status.in_(["completed", "cancelled"]), Task.completed_at.isnot(None),
                Task.completed_at <= cutoff)
        .all()
    ]
    purged = 0
    if closed_ids:
        purged = (
            db.query(ProgressLog)
            .filter(ProgressLog.task_id.in_(closed_ids), ProgressLog.lat.isnot(None))
            .update({"lat": None, "lng": None}, synchronize_session=False)
        )
    return {"purged_logs": purged}


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
    # TASK-033 驳回上限：超过后禁止再单方驳回，须验收或发起纠纷仲裁（防无限返工变相欠薪）
    if task.reject_count >= settings.MAX_REJECT_ROUNDS:
        raise conflict(
            f"已达驳回上限（{settings.MAX_REJECT_ROUNDS} 次），请验收或发起纠纷仲裁",
            "reject_limit_reached",
        )
    task.reject_count += 1
    db.add(ProgressLog(task_id=task_id, user_id=user.id, kind="note", content=f"验收驳回：{body.reason}"))
    service.transition(db, task, "in_progress")
    # 通知执行者被驳回原因，避免其不知情空等（TASK-033）
    if task.executor_id:
        from app.modules.notification.service import notify

        notify(db, task.executor_id, "task", "交付被驳回",
               f"《{task.title}》第 {task.reject_count} 次验收未通过：{body.reason[:80]}。"
               f"剩余可驳回 {settings.MAX_REJECT_ROUNDS - task.reject_count} 次，超限后须验收或仲裁。")
    return dump_task(task, user)


def _complete_task(db: Session, task: Task) -> None:
    """验收通过：放款（SC-005）→ 完成 → 信用更新 → task.completed 事件（经验入库等）。

    RISK-003：同对手方短期高频闭环判定为刷单嫌疑 —— 正常放款（资金无损），
    但不累计信用与完成单数，并自动生成风控工单进入人审队列。
    """
    from app.modules.risk import service as risk

    contract = db.query(Contract).filter(Contract.task_id == task.id).first()
    if contract:
        contract_service.release(db, contract)
    task.completed_at = utcnow()
    suspicious = bool(
        task.executor_id and risk.is_suspicious_pair(db, task.creator_id, task.executor_id)
    )
    service.transition(db, task, "completed")
    if task.executor_id:
        if suspicious:
            risk.flag_pair(db, task)
        else:
            credit.record_task_completed(db, task.executor_id)


@router.post("/tasks/jobs/deadline-alerts")
def run_deadline_alerts(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """AI-DEC-022 逾期预警 job。"""
    from app.modules.decompose.resilience import deadline_alerts

    return {"alerted": deadline_alerts(db, utcnow())}


@router.post("/tasks/jobs/settle-reviews")
def run_settle_reviews(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """CRED-002 评价窗口结算 job：窗口到期的未入账评分统一聚合并公开，
    保证即使无人读取，评分也会在窗口到期后按时入账（真双盲的兜底结算）。"""
    cutoff = utcnow() - timedelta(days=settings.REVIEW_WINDOW_DAYS)
    expired_task_ids = [
        t.id for t in db.query(Task).filter(
            Task.status == "completed", Task.completed_at <= cutoff
        )
    ]
    settled = 0
    if expired_task_ids:
        pending = db.query(Review).filter(
            Review.task_id.in_(expired_task_ids), Review.rating_applied.is_(False)
        ).all()
        _settle_reviews(db, pending)
        settled = len(pending)
    return {"settled": settled}


@router.post("/tasks/jobs/expire-tasks")
def run_expire_tasks(db: Session = Depends(get_db), _=Depends(require_job_auth)):
    """TASK-015 过期任务自动下架：已发布但过了截止时间仍无人成交的任务自动关闭。

    发布时校验了 deadline 必须在未来，但发布后从不执行——僵尸挂单会永远占据广场。
    此 job 把过期未成交的 published 任务转 cancelled，并通知发布者与全部待处理报名者。
    """
    now = utcnow()
    rows = (
        db.query(Task)
        .filter(Task.status == "published", Task.deadline.isnot(None), Task.deadline <= now)
        .all()
    )
    from app.modules.notification.service import notify

    for task in rows:
        service.transition(db, task, "cancelled", {"cancelled_by": "system_expired"})
        notify(db, task.creator_id, "task", "任务已过期下架",
               f"《{task.title}》已过截止时间仍无人成交，已自动下架，可重新发布。")
        apps = db.query(Application).filter(
            Application.task_id == task.id, Application.status == "pending"
        ).all()
        for a in apps:
            a.status = "rejected"
            db.add(a)
            notify(db, a.applicant_id, "task", "报名的任务已下架",
                   f"《{task.title}》已过期下架，你的报名已自动关闭。")
    return {"expired": len(rows)}


@router.post("/tasks/jobs/auto-accept")
def run_auto_accept(db: Session = Depends(get_db), _=Depends(require_job_auth)):
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
    service.transition(db, task, "cancelled", {"cancelled_by": result.get("cancelled_by", "")})
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
    # CRED-002 评价窗口：结项后 N 天内可评，到期不可补评（业界惯例）
    if task.completed_at and utcnow() > task.completed_at + timedelta(days=settings.REVIEW_WINDOW_DAYS):
        raise conflict("评价期已过", "review_window_closed")
    target_id = task.executor_id if user.id == task.creator_id else task.creator_id
    dup = db.query(Review).filter(Review.task_id == task_id, Review.reviewer_id == user.id).first()
    if dup:
        raise conflict("已评价过", "already_reviewed")
    review = Review(
        task_id=task_id, reviewer_id=user.id, target_id=target_id,
        stars=body.stars, tags=body.tags, comment=body.comment,
    )
    db.add(review)
    db.flush()
    # CRED-002 真双盲：评分聚合延迟到公开时点，避免对方通过 rating_avg/信用分变化
    # 反推我打了几星后在窗口内报复。此处仅在双方都评完时才结算两条。
    rows = db.query(Review).filter(Review.task_id == task_id).all()
    if len(rows) >= 2:
        _settle_reviews(db, rows)
    publish(db, "review.submitted", {"task_id": task_id, "target_id": target_id, "stars": body.stars})
    return {"ok": True}


def _settle_reviews(db: Session, rows: list[Review]) -> None:
    """把尚未入账的评分聚合到目标用户（幂等：rating_applied 去重）。"""
    for r in rows:
        if not r.rating_applied:
            credit.record_review(db, r.target_id, r.stars)
            r.rating_applied = True
            db.add(r)


@router.get("/users/{user_id}/reviews")
def user_reviews(
    user_id: int,
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """CRED-006 用户收到的评价（口碑消费端）。

    此前评语/标签只写不读：主页仅有 rating_avg 聚合，选人时看不到「为什么是 4.5 分」。
    严格复用双盲揭晓规则——盲窗内（双方未评完且未到窗口期）的评价一律不返回，
    避免绕过 /tasks/{id}/reviews 的保护从用户维度偷看。
    """
    rows = (
        db.query(Review).filter(Review.target_id == user_id)
        .order_by(Review.id.desc()).all()
    )
    if not rows:
        return {"total": 0, "tag_counts": {}, "items": []}
    task_ids = {r.task_id for r in rows}
    tasks = {t.id: t for t in db.query(Task).filter(Task.id.in_(task_ids))}
    counts: dict[int, int] = {}
    for r in db.query(Review).filter(Review.task_id.in_(task_ids)):
        counts[r.task_id] = counts.get(r.task_id, 0) + 1

    now = utcnow()
    visible = []
    for r in rows:
        t = tasks.get(r.task_id)
        window_expired = bool(
            t and t.completed_at
            and now > t.completed_at + timedelta(days=settings.REVIEW_WINDOW_DAYS)
        )
        if counts.get(r.task_id, 0) >= 2 or window_expired:  # 与单任务视图同一揭晓条件
            visible.append(r)

    tag_counts: dict[str, int] = {}
    for r in visible:
        for tag in (r.tags or []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    page = visible[offset:offset + limit]
    return {
        "total": len(visible),
        "tag_counts": tag_counts,
        "items": [
            {"task_id": r.task_id, "reviewer_id": r.reviewer_id, "stars": r.stars,
             "tags": r.tags, "comment": r.comment, "created_at": r.created_at.isoformat()}
            for r in page
        ],
    }


@router.get("/tasks/{task_id}/reviews")
def list_reviews(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """双盲互评（CRED-002）：双方都评完或窗口到期前，评价只有作者本人（和管理员）
    可见——包括对第三方隐藏，否则换个账号即可偷看，盲评失效。"""
    task = _get_task(db, task_id)
    rows = db.query(Review).filter(Review.task_id == task_id).all()
    both_done = len(rows) >= 2
    window_expired = bool(
        task.completed_at
        and utcnow() > task.completed_at + timedelta(days=settings.REVIEW_WINDOW_DAYS)
    )
    revealed = both_done or window_expired
    # 窗口到期公开时：把单边评价补记入账（真双盲下评分同样延迟到公开时点）
    if revealed:
        _settle_reviews(db, rows)
    out = []
    for r in rows:
        if not revealed and r.reviewer_id != user.id and not user.is_admin:
            continue
        out.append(
            {"reviewer_id": r.reviewer_id, "target_id": r.target_id, "stars": r.stars,
             "tags": r.tags, "comment": r.comment, "revealed": revealed}
        )
    return out
