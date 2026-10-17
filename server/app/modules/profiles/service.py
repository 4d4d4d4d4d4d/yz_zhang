"""PROF-100 任务画像与能力画像（126 号 spec）。

**任务画像**：一单活的结构化描述——形态、技能（写明的 + 从说明里认出的）、规模、价格位置、风险、说明完整度与补全建议。
发布页实时用它提示「还缺什么」，报名的人用它看风险，撮合用它补技能。

**能力画像**：一个人在平台上**被证明过**的能力——做成过哪些类目（星级）、哪些技能有成交佐证、
资质、准时率、返工率、纠纷、回复速度、可用时段。自述与佐证分开写：画像不是简历。

全部由已有数据算出来，不新增表；对外只给聚合数，不给明细。
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

SKILL_VOCAB_LIMIT = 500
ACCEPT_HINT = re.compile(r"验收|标准|交付物|交付|完成后|做到")
RISK_WORDS = {
    "advance": (re.compile(r"垫付|先付|预付"), "需要垫付：金额与凭证提前说清，走平台记录"),
    "onsite_home": (re.compile(r"上门|入户|家里|家中"), "上门服务：注意人身安全，到达后在平台打卡"),
    "minor": (re.compile(r"未成年|孩子|儿童|小孩"), "涉及未成年人：平台要求额外核验，不允许单独相处的安排"),
}


# ------------------------------------------------------------------ 技能词表
def skill_vocab(db: Session) -> list[str]:
    """平台上的技能词：用户自述的技能 + 任务写明的技能，取最常见的 500 个。"""
    from app.modules.account.models import User
    from app.modules.task.models import Task

    c: Counter = Counter()
    for (skills,) in db.query(User.skills).filter(User.is_deleted.is_(False)).limit(5000):
        c.update(s for s in (skills or []) if isinstance(s, str) and 1 < len(s) <= 20)
    for (skills,) in db.query(Task.required_skills).order_by(Task.id.desc()).limit(5000):
        c.update(s for s in (skills or []) if isinstance(s, str) and 1 < len(s) <= 20)
    return [s for s, _ in c.most_common(SKILL_VOCAB_LIMIT)]


def infer_skills(text: str, vocab: list[str], declared: list[str], db: Session | None = None) -> list[str]:
    low = text.lower()
    seen = {s.lower() for s in declared}
    out = []
    for s in sorted(vocab, key=len, reverse=True):
        if s.lower() in low and s.lower() not in seen and not any(s.lower() in o.lower() for o in out):
            out.append(s)
        if len(out) >= 8:
            break
    # PROF-110 / SKL-103 说明里写的是别名（「做个 logo 设计」）也认出来，给规范名（135 号 spec）
    from app.modules.skills.service import aliases_in, canonical, index

    idx = index(db)
    taken = {canonical(x, idx) for x in [*out, *declared]}
    for name in dict.fromkeys(aliases_in(text, db).values()):
        if len(out) >= 8:
            break
        if name not in taken:
            out.append(name)
            taken.add(name)
    return out


# ------------------------------------------------------------------ 创作类需求九项（SCN-106，140 号 spec）
# 类目是这些，或者要求 / 认出的技能（按 135 号概念表的规范名）是这些，就按创作类需求单的九项看缺什么
BRIEF_CATEGORIES = ("设计", "文案", "视频剪辑", "剪辑", "摄影", "插画", "动画")
BRIEF_SKILLS = ("品牌设计", "平面设计", "UI设计", "视频剪辑", "摄影", "文案")


def brief(t: dict, category: str, text: str, skills: list[str]) -> dict | None:
    """创作类的单才有：九项里写到了哪些、没写的该补什么。表单里填了的（预算、截止时间）也算写到。

    只是提示，不计入「说明完整度」——那个分数的口径（126 号）不变。"""
    from app.modules.packs.creator import ITEMS, brief_check

    if category not in BRIEF_CATEGORIES and not set(skills) & set(BRIEF_SKILLS):
        return None
    r = brief_check(text)
    filled = {"预算": int(t.get("budget_cents") or 0) > 0, "交期": bool(t.get("deadline"))}
    items = [{"name": name, "ok": name in r["present"] or filled.get(name, False), "ask": ask} for name, _, ask in ITEMS]
    return {"items": items, "missing": sum(1 for i in items if not i["ok"])}


def _canonical_all(db: Session, skills: list[str]) -> list[str]:
    from app.modules.skills.service import canonical, index

    idx = index(db)
    return [canonical(x, idx) for x in skills]


# ------------------------------------------------------------------ 任务画像（PROF-101~104）
def task_profile(db: Session, t: dict) -> dict:
    """`t` 是任务的字段字典（草稿也行）：title / description / category / budget_cents / is_remote / city /
    lat / deadline / required_skills / acceptance_criteria。"""
    from app.modules.knowledge.service import price_reference
    from app.modules.task.service import get_category

    title, desc = (t.get("title") or "").strip(), (t.get("description") or "").strip()
    text = f"{title}\n{desc}"
    declared = [s for s in (t.get("required_skills") or []) if s]
    inferred = infer_skills(text, skill_vocab(db), declared, db)
    category = t.get("category") or ""
    cat = get_category(db, category) if category else None
    budget = int(t.get("budget_cents") or 0)
    remote = bool(t.get("is_remote"))

    # 价格位置：同类目（优先同城）近 180 天成交分布
    ref = price_reference(db, category, t.get("city") or None) if category else {"sample_size": 0}
    if category and not ref.get("sample_size") and t.get("city"):
        ref = price_reference(db, category, None)
    price = {"sample_size": ref.get("sample_size", 0), "p50_cents": ref.get("p50_cents"),
             "min_cents": ref.get("min_cents"), "max_cents": ref.get("max_cents"), "position": "unknown"}
    if price["sample_size"] and budget:
        p50, lo = price["p50_cents"], price["min_cents"]
        price["position"] = ("below_min" if budget < lo else "below_median" if budget < p50 * 0.9
                             else "above_median" if budget > p50 * 1.1 else "around_median")
    size = ("unknown" if not price["sample_size"] or not budget else
            "small" if budget < price["p50_cents"] * 0.5 else "large" if budget > price["p50_cents"] * 2 else "medium")

    risks = []
    if cat is not None and cat.required_cert:
        risks.append({"kind": "cert", "text": f"这个类目要求「{cat.required_cert}」资质，没有的人报不了名"})
    for kind, (pat, msg) in RISK_WORDS.items():
        if pat.search(text) and not (kind == "onsite_home" and remote):
            risks.append({"kind": kind, "text": msg})
    if budget >= 500_000:
        risks.append({"kind": "large_amount", "text": "金额较大：建议分期（里程碑）托管，每期交付后再放款"})

    # 说明完整度：每一条都是「缺了会出问题」的东西
    acceptance = [a for a in (t.get("acceptance_criteria") or []) if a] or ([1] if ACCEPT_HINT.search(desc) else [])
    checks = [
        ("title", len(title) >= 6, "标题再具体一点：写清做什么、在哪、多大规模（至少 6 个字）"),
        ("description", len(desc) >= 30, "说明再写几句：背景、要做的事、注意事项（至少 30 个字）"),
        ("acceptance", bool(acceptance), "写清验收标准：做到什么程度算完成——验收和纠纷都以它为准"),
        ("deadline", bool(t.get("deadline")), "给一个截止时间：没有截止时间，接单的人没法排期"),
        ("location", remote or bool(t.get("city")) and t.get("lat") is not None, "线下的活要给城市和大致位置：附近的人才看得到"),
        ("budget", budget > 0, "给一个预算：没有预算的单很少有人报名"),
        ("skills", bool(declared or inferred), "写上需要的技能：撮合按技能推荐合适的人"),
    ]
    if price["position"] == "below_min":
        checks.append(("price", False, f"预算低于近期同类成交的最低价（¥{price['min_cents'] / 100:.2f}）：可能没人接"))
    elif price["position"] == "below_median":
        checks.append(("price", False, f"预算低于同类成交中位（¥{price['p50_cents'] / 100:.2f}）：报名会比较少"))
    passed = sum(1 for _, ok, _ in checks if ok)
    return {
        "category": category, "mode": "remote" if remote else "onsite", "declared_skills": declared,
        "inferred_skills": inferred, "size": size, "price": price, "risks": risks,
        "completeness": round(passed / len(checks), 2),
        "checks": [{"key": k, "ok": ok, "hint": "" if ok else hint} for k, ok, hint in checks],
        "brief": brief(t, category, text, _canonical_all(db, declared) + inferred),
    }


def task_fields(task) -> dict:
    return {"title": task.title, "description": task.description, "category": task.category,
            "budget_cents": task.budget_cents, "is_remote": task.is_remote, "city": task.city, "lat": task.lat,
            "deadline": task.deadline, "required_skills": task.required_skills,
            "acceptance_criteria": task.acceptance_criteria}


# ------------------------------------------------------------------ 能力画像（PROF-105~107）
def capability(db: Session, user, public: bool) -> dict:
    """被证明过的能力。`public=True` 时只给对外的聚合（不给纠纷明细与回复样本数）。"""
    from app.modules.dispute.models import Dispute
    from app.modules.matching.service import _reply_hours
    from app.modules.task.models import Review, Task

    done = (db.query(Task).filter(Task.executor_id == user.id, Task.status == "completed")
            .order_by(Task.id.desc()).limit(2000).all())
    stars: dict[int, int] = dict(db.query(Review.task_id, Review.stars)
                                 .filter(Review.target_id == user.id, Review.task_id.in_([t.id for t in done] or [-1])))
    by_cat: dict[str, list[int]] = defaultdict(list)
    for t in done:
        by_cat[t.category].append(stars.get(t.id, 0))
    categories = sorted(({"category": c, "completed": len(v),
                          "rating_avg": round(sum(x for x in v if x) / max(1, sum(1 for x in v if x)), 1) if any(v) else None}
                         for c, v in by_cat.items()), key=lambda x: (-x["completed"], x["category"]))
    evidenced_pool = {s.lower() for t in done for s in (t.required_skills or [])} | {t.category.lower() for t in done}
    claimed = [s for s in (user.skills or []) if isinstance(s, str)]
    from app.modules.skills.service import matcher

    same = matcher(db)
    skills = [{"skill": s, "evidenced": s.lower() in evidenced_pool or any(s.lower() in e for e in evidenced_pool)
               or any(same(s, e) for e in evidenced_pool)} for s in claimed]
    from app.modules.account.cert_service import active_certifications

    # 只认平台核验通过且没过期的资质（CERT-005），不认用户自己填进资料里的名字
    certs = active_certifications(db, user.id)
    with_deadline = [t for t in done if t.deadline and t.delivered_at]
    on_time = (round(sum(1 for t in with_deadline if t.delivered_at <= t.deadline) / len(with_deadline), 2)
               if len(with_deadline) >= 3 else None)
    rework = round(sum(1 for t in done if (t.reject_count or 0) > 0) / len(done), 2) if len(done) >= 3 else None
    disputes = (db.query(func.count(Dispute.id)).join(Task, Task.id == Dispute.task_id)
                .filter(Task.executor_id == user.id).scalar() or 0)
    reply = _reply_hours(db, [user.id]).get(user.id)
    out = {
        "user_id": user.id, "tasks_completed": len(done), "categories": categories[:10], "skills": skills,
        "certifications": [c for c in certs if c], "on_time_rate": on_time, "rework_rate": rework,
        "reply_hours_median": round(reply, 1) if reply is not None else None,
        "has_weekly_slots": bool(user.weekly_slots), "limited_capacity": bool(user.limited_capacity),
        "note": "只统计在平台上完成的单；样本少于 3 单的比率不给出",
    }
    out["disputes"] = None if public else int(disputes)
    return out
