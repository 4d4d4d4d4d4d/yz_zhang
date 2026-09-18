"""编排韧性（AI-DEC-022/023）：子任务违约自动重新招募 + 逾期预警。"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.events import subscribe
from app.modules.task.models import Task
from app.modules.task.service import transition

RESPAWN_FIELDS = [
    "creator_id", "parent_id", "depends_on", "title", "description", "category",
    "task_type", "required_skills", "budget_cents", "pricing", "deposit_cents",
    "is_remote", "city", "lat", "lng", "address_hint", "address_exact",
    "visibility", "circle_id",
]


def _on_task_cancelled(db: Session, payload: dict) -> None:
    """AI-DEC-023：执行者违约导致子任务取消 → 自动复制重新发布，推动母任务继续。"""
    if payload.get("cancelled_by") != "executor":
        return
    task = db.get(Task, payload["task_id"])
    if not task or not task.parent_id:
        return
    respawn = Task(**{f: getattr(task, f) for f in RESPAWN_FIELDS})
    db.add(respawn)
    db.flush()
    transition(db, respawn, "published")
    from app.modules.notification.service import notify

    notify(
        db, task.creator_id, "task", "子任务已自动重新招募",
        f"《{task.title}》因执行者违约取消，系统已自动重新发布（新任务 #{respawn.id}）",
    )


def deadline_alerts(db: Session, now: datetime) -> int:
    """AI-DEC-022 风险预警：执行中任务逾期 → 通知双方（生产为定时任务）。"""
    from app.modules.notification.service import notify

    rows = (
        db.query(Task)
        .filter(Task.status == "in_progress", Task.deadline.isnot(None), Task.deadline < now)
        .all()
    )
    for task in rows:
        notify(db, task.creator_id, "task", "任务已逾期",
               f"《{task.title}》已超过截止时间，建议催办、协商改期或发起纠纷")
        if task.executor_id:
            notify(db, task.executor_id, "task", "任务已逾期",
                   f"《{task.title}》已超过截止时间，请尽快交付或与发布者协商")
    return len(rows)


def register_event_handlers() -> None:
    subscribe("task.cancelled", _on_task_cancelled, retry=True)
