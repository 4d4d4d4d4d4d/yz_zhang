"""任务状态机与审核（03）。"""
from sqlalchemy.orm import Session

from app.core.errors import bad_request, conflict
from app.core.events import publish

from .models import TRANSITIONS, Task

# TASK-004 发布前机审违禁词（RISK-001 简化实现；生产接内容安全服务）
BANNED_WORDS = ["代考", "刷单", "赌博", "毒品", "枪支", "色情", "洗钱"]

# ACC-022 受限类目 → 所需职业资质（运营后台可配的简化版）
# 「法律咨询」类目 = LAW-003 律师市场：持证律师方可接单
RESTRICTED_CATEGORIES = {"法律咨询": "律师", "电工维修": "电工", "燃气维修": "燃气作业"}


def check_category_qualification(task, user) -> None:
    required = RESTRICTED_CATEGORIES.get(task.category)
    if required and required not in (user.certifications or []):
        raise bad_request(f"该类目需「{required}」职业资质认证后方可接单", "certification_required")


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
