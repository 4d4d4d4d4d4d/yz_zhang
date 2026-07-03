"""信用分服务（CRED-001/002/004）与黑名单（ACC-033）。"""
from sqlalchemy.orm import Session

from .models import Block, User


def is_blocked_between(db: Session, user_a: int, user_b: int) -> bool:
    """任一方向拉黑即视为不可互动。"""
    return (
        db.query(Block)
        .filter(
            ((Block.blocker_id == user_a) & (Block.blocked_id == user_b))
            | ((Block.blocker_id == user_b) & (Block.blocked_id == user_a))
        )
        .first()
        is not None
    )

# 信用分增减规则（后台可配的简化版）
CREDIT_TASK_COMPLETED = 2
CREDIT_REVIEW_BONUS = {5: 2, 4: 1, 3: 0, 2: -2, 1: -4}
CREDIT_DISPUTE_LOSER = -10
CREDIT_CANCEL_PENALTY = -5
CREDIT_MIN, CREDIT_MAX = 0, 200


def adjust_credit(db: Session, user_id: int, delta: int) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.credit_score = max(CREDIT_MIN, min(CREDIT_MAX, user.credit_score + delta))
    db.add(user)


def record_review(db: Session, target_user_id: int, stars: int) -> None:
    user = db.get(User, target_user_id)
    if not user:
        return
    user.rating_sum += stars
    user.rating_count += 1
    db.add(user)
    adjust_credit(db, target_user_id, CREDIT_REVIEW_BONUS.get(stars, 0))


def record_task_completed(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if not user:
        return
    user.tasks_completed += 1
    db.add(user)
    adjust_credit(db, user_id, CREDIT_TASK_COMPLETED)
