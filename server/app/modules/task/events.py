"""TASK-006 周期任务：闭环后自动生成并发布下一期。"""
from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import Task
from .service import transition

RECURRENCES = ("none", "weekly", "monthly")

COPY_FIELDS = [
    "creator_id", "title", "description", "category", "task_type", "required_skills",
    "budget_cents", "pricing", "is_remote", "city", "lat", "lng",
    "address_hint", "address_exact", "visibility", "circle_id", "recurrence",
]


def _on_task_completed(db: Session, payload: dict) -> None:
    task = db.get(Task, payload["task_id"])
    if not task or task.recurrence == "none" or task.parent_id:
        return
    next_task = Task(**{f: getattr(task, f) for f in COPY_FIELDS}, recurred_from_id=task.id)
    db.add(next_task)
    db.flush()
    transition(db, next_task, "published")
    from app.modules.notification.service import notify

    notify(
        db, task.creator_id, "task", "周期任务已续期",
        f"《{task.title}》已按{'每周' if task.recurrence == 'weekly' else '每月'}周期自动发布下一期",
    )


def register_event_handlers() -> None:
    # EVT-022 唯一标为不可重试的：它会**创建一个带预算的新任务**。
    # 几小时后由后台悄悄补出来一单，比缺这一期更糟——留给人去决定。
    subscribe("task.completed", _on_task_completed, retry=False)
