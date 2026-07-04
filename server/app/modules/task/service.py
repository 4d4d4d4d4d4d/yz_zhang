"""任务状态机与审核（03）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.core.events import publish

from .models import TRANSITIONS, Task

# TASK-004 发布前机审违禁词（RISK-001 简化实现；生产接内容安全服务）
BANNED_WORDS = ["代考", "刷单", "赌博", "毒品", "枪支", "色情", "洗钱"]

# OPS-004 类目种子（首次启动写入 Category 表，此后运营后台维护）
SEED_CATEGORIES = [
    {"name": "保洁"}, {"name": "跑腿"}, {"name": "维修"}, {"name": "软件开发"},
    {"name": "设计"}, {"name": "活动策划"}, {"name": "二手交易"},
    # LAW-003 律师市场 / 高危作业准入（ACC-022）
    {"name": "法律咨询", "required_cert": "律师"},
    {"name": "电工维修", "required_cert": "电工"},
    {"name": "燃气维修", "required_cert": "燃气作业"},
]


def seed_categories(db: Session) -> None:
    from .models import Category

    if db.query(Category).first():
        return
    for c in SEED_CATEGORIES:
        db.add(Category(**c))
    db.flush()


def get_category(db: Session, name: str):
    from .models import Category

    return db.query(Category).filter(Category.name == name).first()


def check_category_qualification(db: Session, task, user) -> None:
    """ACC-022 受限类目准入（读类目表，运营后台可配）。"""
    category = get_category(db, task.category)
    required = category.required_cert if category else ""
    if required and required not in (user.certifications or []):
        raise bad_request(f"该类目需「{required}」职业资质认证后方可接单", "certification_required")


def validate_category(db: Session, name: str) -> None:
    category = get_category(db, name)
    if not category or not category.active:
        raise bad_request(f"类目「{name}」不存在或已停用", "invalid_category")


def machine_review(text: str) -> str | None:
    for word in BANNED_WORDS:
        if word in text:
            return word
    return None


def transition(db: Session, task: Task, new_status: str, event_payload: dict | None = None):
    """唯一合法的状态变更入口（统一审计 + 事件派发）。"""
    allowed = TRANSITIONS.get(task.status, set())
    if new_status not in allowed:
        raise conflict(f"任务状态不允许从 {task.status} 变更为 {new_status}", "invalid_transition")
    old = task.status
    task.status = new_status
    db.add(task)
    db.flush()
    publish(db, f"task.{new_status}", {"task_id": task.id, "from": old, **(event_payload or {})})


def validate_publishable(task: Task) -> None:
    if task.budget_cents <= 0:
        raise bad_request("预算必须大于 0", "budget_required")
    hit = machine_review(task.title + " " + task.description)
    if hit:
        raise bad_request(f"内容含违禁信息（{hit}），发布被拒绝", "content_rejected")
    if not task.is_remote and (task.lat is None or task.lng is None):
        raise bad_request("线下任务必须提供位置", "location_required")
