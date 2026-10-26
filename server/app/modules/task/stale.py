"""AI-DEC-023 的安全一半（320 号 spec）：招募多天没人报名时提醒发单人，并给一个「再推一次」。

没人报名的单（母任务下的子任务尤其）会一直停在那里，整单跟着卡住。全自动的重新招募要碰预算（加价、调剂），
那要发单人事先授权，这一批不做；这里只做两件不碰钱的事：
- 每天查一遍：发布超过 3 天、一条报名都没有的单，提醒发单人（同一单每 3 天最多一次）；
- 发单人在任务页一键「再推一次」（可以顺带加价，加价走已发布任务本来就有的规则）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.modules.account.models import utcnow

from .cockpit import STALE_RECRUIT_DAYS
from .models import Application, Task

STALE_TITLE = "「{title}」招募 {days} 天还没人报名"
STALE_BODY = "在任务页点「再推一次」让附近的人再看到它（可以顺带加价），或者改改说明、主动邀约合适的人。"
SLOTS_TITLE = "「{title}」有 {n} 个名额招募 {days} 天还没人报名"
SLOTS_BODY = "在任务页缺人的那天点「补招」（可以顺带加价、邀请那天有空的人），或者改改说明。"


def has_children(t: Task) -> bool:
    """带子任务的母任务（项目、一单多人或多天）：报名都在子任务上，它自己永远「没人报名」。"""
    return t.parent_id is None and (t.task_type == "project" or (t.days or 1) > 1 or (t.people_needed or 1) > 1)


def remind_stale_recruits(db: Session, now: datetime | None = None) -> dict:
    from app.modules.notification.service import notify

    now = now or utcnow()
    cutoff = now - timedelta(days=STALE_RECRUIT_DAYS)
    rows = (db.query(Task).filter(Task.status == "published", Task.executor_id.is_(None), Task.created_at < cutoff,
                                  (Task.stale_reminded_at.is_(None)) | (Task.stale_reminded_at < cutoff))
            .order_by(Task.id).all())
    reminded = 0
    slots_by_parent: dict[int, tuple[Task, list[Task]]] = {}
    for t in rows:
        if has_children(t):
            continue                                  # 母任务自己不提醒：看它下面的子任务、名额
        if db.query(Application.id).filter(Application.task_id == t.id).first() is not None:
            continue
        parent = db.get(Task, t.parent_id) if t.parent_id else None
        if parent is not None and parent.task_type != "project":
            slots_by_parent.setdefault(parent.id, (parent, []))[1].append(t)   # 名额：同一单合成一条
            continue
        days = (now - t.created_at).days
        notify(db, t.creator_id, "task", STALE_TITLE.format(title=t.title, days=days), STALE_BODY)
        t.stale_reminded_at = now
        db.add(t)
        reminded += 1
    for parent, slots in slots_by_parent.values():
        days = (now - min(s.created_at for s in slots)).days
        notify(db, parent.creator_id, "task", SLOTS_TITLE.format(title=parent.title, n=len(slots), days=days), SLOTS_BODY)
        for s in slots:
            s.stale_reminded_at = now
            db.add(s)
        reminded += 1
    return {"reminded": reminded}
