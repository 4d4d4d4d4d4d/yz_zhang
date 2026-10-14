"""AI 推荐人选打分引擎（MATCH-002）。

MVP 为可解释的特征加权模型：技能匹配 40% + 信用 25% + 距离 20% + 评价 15%。
特征权重后续由管理后台配置（MATCH-008），并可替换为学习排序模型。
"""
from sqlalchemy.orm import Session

from app.core.geoutil import haversine_m
from app.modules.account.models import User

WEIGHTS = {"skill": 0.40, "credit": 0.25, "distance": 0.20, "rating": 0.15}


def get_weights(db: Session) -> dict:
    """MATCH-008：优先读后台配置，无配置用默认。"""
    from .models import MatchingConfig

    row = db.get(MatchingConfig, "weights")
    if row and row.data:
        return {**WEIGHTS, **row.data}
    return WEIGHTS


def _skill_score(task_skills: list[str], user_skills: list[str], same=None) -> float:
    if not task_skills:
        return 0.5  # 无技能要求时给中性分
    if same is None:
        hit = len(set(task_skills) & set(user_skills))
    else:
        # SKL-102 按技能概念比（135 号 spec）：「VI 设计」与「品牌设计」算同一项；写法完全相同的照旧算
        hit = sum(1 for t in dict.fromkeys(task_skills) if any(same(t, u) for u in user_skills or [] if isinstance(u, str)))
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


# SPACE-023 相关性加分：叠加在可配置的四项加权之上，不改后台配置的权重
FIT_APPLIED = 0.10       # 已经报名这一单：明确表达了意愿
FIT_DONE_CATEGORY = 0.15  # 在这个类目做成过（平台上闭环的事实，最硬的信号）
FIT_MENTIONS = 0.08      # 技能或个人空间里写着这个类目（自述，权重低于做成过）


def _category_fit(db: Session, task, users: list[User]) -> dict[int, tuple[float, list[str]]]:
    """每个候选人与这一单的相关性：一次取齐（与候选人数无关的三条查询）。"""
    from sqlalchemy import func

    from app.modules.spaces.models import PersonalSpace
    from app.modules.task.models import Application, Task

    user_ids = [u.id for u in users]
    if not user_ids or not task.category:
        return {}
    applied = {a for (a,) in db.query(Application.applicant_id).filter(Application.task_id == task.id)}
    done = dict(db.query(Task.executor_id, func.count(Task.id)).filter(
        Task.executor_id.in_(user_ids), Task.category == task.category, Task.status == "completed",
    ).group_by(Task.executor_id))
    spaces = {s.user_id: s for s in db.query(PersonalSpace).filter(
        PersonalSpace.user_id.in_(user_ids), PersonalSpace.published.is_(True))}
    skills = {u.id: u.skills for u in users}
    cat = task.category
    # PROF-104 发布方没写技能要求时，从标题与说明里认出技能（126 号 spec）：只加分，不改原有的技能匹配
    inferred: list[str] = []
    if not task.required_skills:
        from app.modules.profiles.service import infer_skills, skill_vocab

        inferred = infer_skills(f"{task.title}\n{task.description}", skill_vocab(db), [], db)
    # INF-104 专家等级（127 号 spec）：只加分，不改原有的打分
    from app.modules.influence.service import TIER_NAMES, tiers_for

    tiers = tiers_for(db, users, cat)
    # SPACE-023b / SKL-104 个人空间与技能里写的是类目的别名也算（「做 VI」≈「品牌设计」，135 号 spec）
    from app.modules.skills.service import concepts, matcher, norm

    same = matcher(db)
    cat_words = next(([c["name"], *c["aliases"]] for c in concepts(db) if c["name"] == cat or cat in c["aliases"]), [cat])
    out: dict[int, tuple[float, list[str]]] = {}
    for uid in user_ids:
        bonus, why = 0.0, []
        if uid in applied:
            bonus += FIT_APPLIED
            why.append("已报名这一单")
        if done.get(uid):
            bonus += FIT_DONE_CATEGORY
            why.append(f"做成过 {done[uid]} 单「{cat}」")
        else:
            sp = spaces.get(uid)
            text = " ".join([*(skills.get(uid) or []),
                             *([sp.headline, sp.introduction] + [i.get("title", "") + i.get("summary", "") for i in sp.items]
                               if sp else [])])
            if any(norm(w) in norm(text) for w in cat_words):
                bonus += FIT_MENTIONS
                why.append(f"擅长「{cat}」（本人技能或个人空间）")
        lvl = tiers.get(uid, "newcomer")
        if FIT_TIER.get(lvl):
            bonus += FIT_TIER[lvl]
            why.append(f"「{cat}」{TIER_NAMES[lvl]}（平台影响力）")
        hit = [s for s in inferred if any(same(s, x) for x in (skills.get(uid) or []) if isinstance(x, str))]
        if hit:
            bonus += FIT_INFERRED_SKILL
            why.append(f"说明里提到了你的技能「{'、'.join(hit[:2])}」")
        if bonus:
            out[uid] = (bonus, why)
    return out


FIT_INFERRED_SKILL = 0.05     # PROF-104：说明里认出的技能与本人技能对上
FIT_TIER = {"skilled": 0.02, "expert": 0.05, "expert_senior": 0.08}   # INF-104 类目等级

# SPACE-023 可用性：时段只回答「有没有空」，回复时长样本够了才说
FIT_FREE_BEFORE_DEADLINE = 0.04
FIT_NO_SLOT_BEFORE_DEADLINE = -0.06
FIT_FAST_REPLY = 0.03
FIT_LIMITED = -0.03
REPLY_MIN_SAMPLES = 5          # 与 Upwork 同一做法：样本不够不给标签
REPLY_FAST_HOURS = 12


def has_slot_between(slots: list[dict], start, end) -> bool:
    """[start, end) 之间（UTC 朴素值）是否落着本人设的任何一个每周时段（北京时间）。"""
    from datetime import timedelta, timezone
    from zoneinfo import ZoneInfo

    if not slots or end <= start:
        return False
    tz = ZoneInfo("Asia/Shanghai")
    s_loc = start.replace(tzinfo=timezone.utc).astimezone(tz)
    e_loc = end.replace(tzinfo=timezone.utc).astimezone(tz)
    day = s_loc.replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(15):       # 最多看两周：每周时段两周内一定会出现一次
        if day > e_loc:
            break
        for sl in slots:
            if sl.get("d") != day.weekday():
                continue
            fh, fm = (int(x) for x in sl["from"].split(":"))
            th, tm = (int(x) for x in sl["to"].split(":"))
            a = day.replace(hour=fh, minute=fm)
            b = day + timedelta(hours=th, minutes=tm)
            if a < e_loc and b > s_loc:
                return True
        day += timedelta(days=1)
    return False


def _reply_hours(db: Session, user_ids: list[int]) -> dict[int, float]:
    """回复邀约的中位时长（小时），样本 ≥ REPLY_MIN_SAMPLES 才给。一次查询。"""
    from statistics import median

    from .models import Invitation

    by: dict[int, list[float]] = {}
    for uid, created, responded in db.query(Invitation.invitee_id, Invitation.created_at, Invitation.responded_at).filter(
            Invitation.invitee_id.in_(user_ids or [-1]), Invitation.responded_at.isnot(None)):
        by.setdefault(uid, []).append((responded - created).total_seconds() / 3600)
    return {uid: median(xs) for uid, xs in by.items() if len(xs) >= REPLY_MIN_SAMPLES}


def _availability(db: Session, task, users: list[User]) -> dict[int, tuple[float, list[str]]]:
    from app.modules.account.models import utcnow

    now = utcnow()
    replies = _reply_hours(db, [u.id for u in users])
    out: dict[int, tuple[float, list[str]]] = {}
    for u in users:
        bonus, why = 0.0, []
        if u.weekly_slots and not task.is_remote:
            end = task.deadline if task.deadline and task.deadline > now else None
            if end is not None:
                if has_slot_between(u.weekly_slots, now, end):
                    bonus += FIT_FREE_BEFORE_DEADLINE
                    why.append("截止前有空（按本人设的时段）")
                else:
                    bonus += FIT_NO_SLOT_BEFORE_DEADLINE     # 只降权、不写进理由：不替他公开日程
        h = replies.get(u.id)
        if h is not None:
            why.append(f"通常 {max(1, round(h))} 小时内回复邀约")
            if h <= REPLY_FAST_HOURS:
                bonus += FIT_FAST_REPLY
        if u.limited_capacity:
            bonus += FIT_LIMITED
            why.append("这阵子少量接单")
        if bonus or why:
            out[u.id] = (bonus, why)
    return out


def recommend(db: Session, task, limit: int = 10) -> list[dict]:
    from app.modules.account.models import Block

    # 召回：实名认证 + 非发布者本人 + 接单开关开启（ACC-014）；
    # 技能召回 + 同城召回的并集（MVP 全量扫，规模化换索引）
    # AGT-018 **显式排除 agent**。agent 全部满足「实名 + 开启接单 + 非发布者」，
    # 不排的话每一个保洁单的推荐列表里都会出现 AI 助理。
    # 能接的 agent 由 `agent.service.eligible_agents()` 单独追加（见下）。
    candidates = (
        db.query(User).filter(User.is_verified.is_(True), User.id != task.creator_id,
                              User.accepting_orders.is_(True),
                              User.is_agent.is_(False),
                              User.is_venture.is_(False),
                              User.is_team.is_(False)).all()
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
    weights = get_weights(db)
    # CIR-010 同圈信任加成：发布者所在圈层的活跃成员集合
    from app.modules.circle.models import CircleMember

    creator_circles = {
        m.circle_id
        for m in db.query(CircleMember).filter(
            CircleMember.user_id == task.creator_id, CircleMember.status == "active"
        )
    }
    same_circle_users = set()
    if creator_circles:
        same_circle_users = {
            m.user_id
            for m in db.query(CircleMember).filter(
                CircleMember.circle_id.in_(creator_circles), CircleMember.status == "active"
            )
        }
    fit = _category_fit(db, task, candidates)
    avail = _availability(db, task, candidates)
    from app.modules.skills.service import matcher

    same = matcher(db)
    scored = []
    for user in candidates:
        skill = _skill_score(task.required_skills, user.skills, same)
        credit = min(user.credit_score, 200) / 200
        distance = _distance_score(task, user)
        rating = user.rating_avg / 5 if user.rating_count else 0.4
        total = (
            weights["skill"] * skill
            + weights["credit"] * credit
            + weights["distance"] * distance
            + weights["rating"] * rating
        )
        # MATCH-002 可解释推荐理由
        reasons = []
        if user.id in same_circle_users:
            total += 0.05  # CIR-010 同圈信任加成
            reasons.append("同圈成员")
        # SPACE-023 与这一单相关的信号（V140 演示：设计单里保洁师傅排在报了名的设计师前面）
        bonus, why = fit.get(user.id, (0.0, []))
        total += bonus
        reasons.extend(why)
        bonus, why = avail.get(user.id, (0.0, []))
        total += bonus
        reasons.extend(why)
        # 任务没写技能要求时 skill 是中性的 0.5——那不是「部分匹配」，不能这样写给人看
        if task.required_skills and skill >= 0.99:
            reasons.append("技能完全匹配")
        elif task.required_skills and skill > 0:
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
                "score": round(max(0.0, min(total, 1.0)), 4),
                "credit_score": user.credit_score,
                "rating_avg": user.rating_avg,
                "skills": user.skills,
                "reasons": reasons or ["新人扶持推荐"],  # MATCH-009 冷启动兜底
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]
