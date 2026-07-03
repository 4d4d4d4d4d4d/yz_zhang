"""AI 推荐人选打分引擎（MATCH-002）。

MVP 为可解释的特征加权模型：技能匹配 40% + 信用 25% + 距离 20% + 评价 15%。
特征权重后续由管理后台配置（MATCH-008），并可替换为学习排序模型。
"""
from sqlalchemy.orm import Session

from app.core.geoutil import haversine_m
from app.modules.account.models import User

WEIGHTS = {"skill": 0.40, "credit": 0.25, "distance": 0.20, "rating": 0.15}


def _skill_score(task_skills: list[str], user_skills: list[str]) -> float:
    if not task_skills:
        return 0.5  # 无技能要求时给中性分
    hit = len(set(task_skills) & set(user_skills))
    return hit / len(task_skills)


def _distance_score(task, user: User) -> float:
    if task.is_remote:
        return 1.0
    if task.lat is None or user.lat is None:
        return 0.3
    d = haversine_m(task.lat, task.lng, user.lat, user.lng)
    if d <= 1000:
        return 1.0
    if d >= 20000:
        return 0.0
    return 1.0 - (d - 1000) / 19000


def recommend(db: Session, task, limit: int = 10) -> list[dict]:
    from app.modules.account.models import Block

    # 召回：实名认证 + 非发布者本人；技能召回 + 同城召回的并集（MVP 全量扫，规模化换索引）
    candidates = (
        db.query(User).filter(User.is_verified.is_(True), User.id != task.creator_id).all()
    )
    # ACC-033 黑名单：双向排除
    blocked_pairs = {
        (b.blocker_id, b.blocked_id)
        for b in db.query(Block).filter(
            (Block.blocker_id == task.creator_id) | (Block.blocked_id == task.creator_id)
        )
    }
    candidates = [
        u for u in candidates
        if (task.creator_id, u.id) not in blocked_pairs and (u.id, task.creator_id) not in blocked_pairs
    ]
    scored = []
    for user in candidates:
        skill = _skill_score(task.required_skills, user.skills)
        credit = min(user.credit_score, 200) / 200
        distance = _distance_score(task, user)
        rating = user.rating_avg / 5 if user.rating_count else 0.4
        total = (
            WEIGHTS["skill"] * skill
            + WEIGHTS["credit"] * credit
            + WEIGHTS["distance"] * distance
            + WEIGHTS["rating"] * rating
        )
        # MATCH-002 可解释推荐理由
        reasons = []
        if skill >= 0.99:
            reasons.append("技能完全匹配")
        elif skill > 0:
            reasons.append("技能部分匹配")
        if credit >= 0.6:
            reasons.append(f"信用分 {user.credit_score}")
        if not task.is_remote and distance >= 0.9:
            reasons.append("距离很近")
        if user.rating_count:
            reasons.append(f"历史评分 {user.rating_avg}")
        if user.tasks_completed:
            reasons.append(f"已完成 {user.tasks_completed} 单")
        scored.append(
            {
                "user_id": user.id,
                "nickname": user.nickname,
                "score": round(total, 4),
                "credit_score": user.credit_score,
                "rating_avg": user.rating_avg,
                "skills": user.skills,
                "reasons": reasons or ["新人扶持推荐"],  # MATCH-009 冷启动兜底
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
