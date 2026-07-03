"""TASK-042/MATCH-003：任务发布事件 → 通知订阅者。"""
from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import Subscription


def _on_task_published(db: Session, payload: dict) -> None:
    from app.modules.notification.service import notify
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task or task.visibility != "public":
        return
    subs = db.query(Subscription).filter(Subscription.category == task.category).all()
    notified = set()
    for sub in subs:
        if sub.user_id == task.creator_id or sub.user_id in notified:
            continue
        if sub.city and task.city and sub.city != task.city:
            continue
        notified.add(sub.user_id)
        notify(
            db, sub.user_id, "task", "订阅类目有新任务",
            f"《{task.title}》（{task.category}·{task.budget_cents / 100:.2f} 元）刚刚发布",
        )


def register_event_handlers() -> None:
    subscribe("task.published", _on_task_published)
