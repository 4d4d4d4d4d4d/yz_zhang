"""通知（NTF-004）：领域事件 → 站内信模板。生产追加 APNs/FCM/短信通道。"""
from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import Notification


def notify(db: Session, user_id: int, category: str, title: str, body: str = "") -> None:
    db.add(Notification(user_id=user_id, category=category, title=title, body=body))


def _task(db: Session, task_id: int):
    from app.modules.task.models import Task

    return db.get(Task, task_id)


def _on_task_matched(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "task", "报名被采纳",
               f"你已被选为任务《{task.title}》的执行者，请尽快签署合约")


def _on_contract_funded(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "funds", "资金已托管",
               f"任务《{task.title}》资金已托管，可以开始执行")


def _on_contract_released(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "funds", "任务款已到账",
               f"任务《{task.title}》验收通过，款项已入钱包")


def _on_task_pending_acceptance(db, payload):
    task = _task(db, payload["task_id"])
    if task:
        notify(db, task.creator_id, "task", "待验收提醒",
               f"任务《{task.title}》已提交验收，超时将自动通过")


def _on_dispute_opened(db, payload):
    for uid in payload.get("parties", []):
        notify(db, uid, "task", "纠纷已受理",
               "相关资金已冻结，请在 48 小时内协商或提交证据")


def register_event_handlers() -> None:
    subscribe("task.matched", _on_task_matched)
    subscribe("contract.funded", _on_contract_funded)
    subscribe("contract.released", _on_contract_released)
    subscribe("task.pending_acceptance", _on_task_pending_acceptance)
    subscribe("dispute.opened", _on_dispute_opened)
