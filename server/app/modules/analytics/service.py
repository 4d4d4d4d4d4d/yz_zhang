"""埋点漏斗、搜索热词、邀请裂变归因（13.C / SRCH-003 / CNT-022）。"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import AnalyticsEvent, SearchQuery


def track(db: Session, name: str, user_id=None, ref_type="", ref_id=None) -> None:
    db.add(AnalyticsEvent(name=name, user_id=user_id, ref_type=ref_type, ref_id=ref_id))


def log_search(db: Session, term: str) -> None:
    term = term.strip()[:100]
    if term:
        db.add(SearchQuery(term=term))


def trending_terms(db: Session, limit: int = 10) -> list[dict]:
    rows = (
        db.query(SearchQuery.term, func.count(SearchQuery.id).label("c"))
        .group_by(SearchQuery.term)
        .order_by(func.count(SearchQuery.id).desc())
        .limit(limit)
        .all()
    )
    return [{"term": t, "count": c} for t, c in rows]


def suggest_terms(db: Session, prefix: str, limit: int = 8) -> list[str]:
    if not prefix:
        return [r["term"] for r in trending_terms(db, limit)]
    rows = (
        db.query(SearchQuery.term, func.count(SearchQuery.id).label("c"))
        .filter(SearchQuery.term.startswith(prefix))
        .group_by(SearchQuery.term)
        .order_by(func.count(SearchQuery.id).desc())
        .limit(limit)
        .all()
    )
    return [t for t, _ in rows]


def _count(db: Session, name: str) -> int:
    return db.query(AnalyticsEvent).filter(AnalyticsEvent.name == name).count()


def funnels(db: Session) -> dict:
    """13.C 发布漏斗 + 接单漏斗（P0）。用任务/合约状态直接聚合，稳健于埋点缺失。"""
    from app.modules.contract.models import Contract
    from app.modules.task.models import Application, Task

    total_tasks = db.query(Task).filter(Task.parent_id.is_(None)).count()
    published = db.query(Task).filter(Task.parent_id.is_(None), Task.status != "draft").count()
    matched = (
        db.query(Task)
        .filter(Task.parent_id.is_(None),
                Task.status.in_(["matched", "in_progress", "pending_acceptance",
                                 "completed", "disputed"]))
        .count()
    )
    completed = db.query(Task).filter(Task.parent_id.is_(None), Task.status == "completed").count()

    applications = db.query(Application).count()
    accepted = db.query(Application).filter(Application.status == "accepted").count()
    contracts_done = db.query(Contract).filter(Contract.status == "released").count()

    def rate(a, b):
        return round(a / b, 3) if b else 0.0

    return {
        "publish_funnel": {
            "created": total_tasks,
            "published": published,
            "matched": matched,
            "completed": completed,
            "publish_rate": rate(published, total_tasks),
            "match_rate": rate(matched, published),
            "complete_rate": rate(completed, matched),
        },
        "worker_funnel": {
            "applications": applications,
            "accepted": accepted,
            "settled": contracts_done,
            "accept_rate": rate(accepted, applications),
        },
        "custom_events": {
            e.name: c
            for e, c in db.query(AnalyticsEvent, func.count(AnalyticsEvent.id))
            .group_by(AnalyticsEvent.name)
            .all()
        },
    }


# ---------- CNT-022 邀请裂变：首单闭环 → 奖励邀请人 ----------
REFERRAL_BONUS = 5  # 信用分奖励


def _on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.account import service as credit
    from app.modules.account.models import User
    from app.modules.notification.service import notify
    from app.modules.task.models import Task

    task = db.get(Task, payload["task_id"])
    if not task or not task.executor_id:
        return
    executor = db.get(User, task.executor_id)
    if not executor or not executor.referred_by or executor.referral_rewarded:
        return
    # 被邀请人完成首单 → 邀请人得信用奖励（每人一次）
    inviter = db.get(User, executor.referred_by)
    if inviter:
        credit.adjust_credit(db, inviter.id, REFERRAL_BONUS)
        notify(db, inviter.id, "system", "邀请奖励到账",
               f"你邀请的「{executor.nickname}」完成首单，信用分 +{REFERRAL_BONUS}")
    executor.referral_rewarded = True
    db.add(executor)


def register_event_handlers() -> None:
    subscribe("task.completed", _on_task_completed)
