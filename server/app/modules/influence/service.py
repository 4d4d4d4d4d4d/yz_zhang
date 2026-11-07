"""影响力的计算部分（127 号 spec）：挣、罚、恢复、衰减、等级、担保、快照与 Merkle 证明。

几条硬规则：
- **只能靠闭环合作挣**：完成一单（执行方）、发的单做成了（发单方，少量）、担保的人做成了（担保人，少量）。
  评分不记成事件——双盲评价揭晓前写进账本就等于提前泄露星级；只在读的时候把**已揭晓**的评价算进来。
- **同一对人反复成交逐单递减**：第 n 单只记 1/n——两个人互刷不能刷出专家。
- **不可转让**：账本只有「本人挣的 / 本人被罚的」，没有任何转让接口。
- **按半衰期衰减**（180 天）：一年前的成绩只剩四分之一，专家要持续做成事才保得住。
- **罚没**：纠纷里执行方拿到不足一半 → 罚该类目当前影响力的 30%（至少 10 点）；为他担保的人罚没担保额的一半。
  申诉改判后补一条恢复事件（账本只增不改）。
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.account.models import utcnow

from .models import InfluenceEvent, InfluenceSnapshot, InfluenceVouch

HALF_LIFE_DAYS = 180
PAIR_WINDOW_DAYS = 90
SLASH_RATE = 0.3
SLASH_MIN = 10.0
VOUCH_SLASH_RATE = 0.5
VOUCH_REWARD_RATE = 0.1
VOUCH_MAX_SHARE = 0.5          # 担保额合计不超过自己在这个类目影响力的一半
LOSE_BELOW_BPS = 5000          # 执行方拿到不足一半 = 败诉
TIERS = [  # (key, 名称, 影响力, 完成单数, 平均星级, 多少天内不能被罚)
    ("expert_senior", "资深专家", 300.0, 30, 4.7, 365),
    ("expert", "专家", 120.0, 10, 4.5, 180),
    ("skilled", "熟手", 30.0, 3, None, None),
    ("newcomer", "新手", 0.0, 0, None, None),
]
TIER_NAMES = {k: n for k, n, *_ in TIERS}
TIER_RANK = {k: i for i, (k, *_) in enumerate(reversed(TIERS))}   # newcomer 0 … expert_senior 3


def decay(points: float, at: datetime, now: datetime) -> float:
    age = max((now - at).total_seconds() / 86400, 0)
    return points * 0.5 ** (age / HALF_LIFE_DAYS)


def _record(db: Session, user_id: int, category: str, kind: str, points: float, ref_type: str, ref_id: int,
            reason: str) -> InfluenceEvent | None:
    """幂等：同一 (人, 种类, 对象) 只记一次。"""
    exists = db.query(InfluenceEvent.id).filter(InfluenceEvent.user_id == user_id, InfluenceEvent.kind == kind,
                                               InfluenceEvent.ref_type == ref_type, InfluenceEvent.ref_id == ref_id).first()
    if exists:
        return None
    ev = InfluenceEvent(user_id=user_id, category=category or "", kind=kind, points=round(points, 2),
                        ref_type=ref_type, ref_id=ref_id, reason=reason[:200])
    try:
        with db.begin_nested():
            db.add(ev)
            db.flush()
    except IntegrityError:
        return None
    return ev


def task_weight(budget_cents: int) -> float:
    """一单值多少：10 点 × (1 + log10(1 + 预算/100 元))，封顶 3 倍。大单多一点，但不线性——刷大单没用。"""
    return 10 * min(3.0, 1 + math.log10(1 + max(budget_cents, 0) / 10000))


# ------------------------------------------------------------------ 挣（INF-101）
def on_task_completed(db: Session, payload: dict) -> None:
    from app.modules.dispute.models import Dispute
    from app.modules.task.models import Task

    t = db.get(Task, payload["task_id"])
    if t is None or not t.executor_id or t.executor_id == t.creator_id:
        return
    d = (db.query(Dispute).filter(Dispute.task_id == t.id, Dispute.verdict_executor_share_bps.isnot(None))
         .order_by(Dispute.id.desc()).first())
    share = 1.0 if d is None else d.verdict_executor_share_bps / 10000
    if share < LOSE_BELOW_BPS / 10000:
        return                                   # 败诉的单不挣（罚没在 dispute.resolved 里）
    since = utcnow() - timedelta(days=PAIR_WINDOW_DAYS)
    nth = (db.query(func.count(Task.id)).filter(Task.creator_id == t.creator_id, Task.executor_id == t.executor_id,
                                                Task.status == "completed", Task.completed_at >= since).scalar() or 1)
    base = task_weight(t.budget_cents) * share / max(nth, 1)
    why = f"完成「{t.title[:40]}」" + (f"（与同一发单方近 {PAIR_WINDOW_DAYS} 天第 {nth} 单，只记 1/{nth}）" if nth > 1 else "")
    _record(db, t.executor_id, t.category, "earn_task", base, "task", t.id, why)
    _record(db, t.creator_id, t.category, "earn_publish", base * 0.2 / 1, "task", t.id, f"发的「{t.title[:40]}」做成了")
    # 为这一单（或这个类目）作保的人：对方做成了，担保释放并得一点
    for v in db.query(InfluenceVouch).filter(InfluenceVouch.subject_id == t.executor_id, InfluenceVouch.status == "active",
                                             InfluenceVouch.task_id == t.id):
        v.status, v.resolved_at = "released", utcnow()
        db.add(v)
        _record(db, v.voucher_id, v.category, "earn_vouch", v.stake * VOUCH_REWARD_RATE, "vouch", v.id,
                f"你担保的人做成了「{t.title[:40]}」")


# ------------------------------------------------------------------ 罚与恢复（INF-103）
def on_dispute_resolved(db: Session, payload: dict) -> None:
    from app.modules.dispute.models import Dispute
    from app.modules.task.models import Task

    d = db.get(Dispute, payload["dispute_id"])
    t = db.get(Task, payload["task_id"])
    if d is None or t is None or not t.executor_id or d.verdict_executor_share_bps is None:
        return
    lost = d.verdict_executor_share_bps < LOSE_BELOW_BPS
    slash = db.query(InfluenceEvent).filter(InfluenceEvent.user_id == t.executor_id, InfluenceEvent.kind == "slash_dispute",
                                           InfluenceEvent.ref_type == "dispute", InfluenceEvent.ref_id == d.id).first()
    if lost and slash is None:
        current = effective(db, [t.executor_id], t.category).get(t.executor_id, 0.0)
        amount = max(SLASH_MIN, current * SLASH_RATE)
        _record(db, t.executor_id, t.category, "slash_dispute", -amount, "dispute", d.id,
                f"「{t.title[:40]}」纠纷败诉（拿到 {d.verdict_executor_share_bps / 100:.0f}%）")
        for v in db.query(InfluenceVouch).filter(InfluenceVouch.subject_id == t.executor_id, InfluenceVouch.status == "active",
                                                 (InfluenceVouch.task_id == t.id)
                                                 | (InfluenceVouch.task_id.is_(None) & (InfluenceVouch.category == t.category))):
            v.status, v.resolved_at, v.dispute_id = "slashed", utcnow(), d.id
            db.add(v)
            _record(db, v.voucher_id, v.category, "slash_vouch", -v.stake * VOUCH_SLASH_RATE, "vouch", v.id,
                    f"你担保的人在「{t.title[:40]}」纠纷败诉，罚没担保额的一半")
    elif not lost and slash is not None:
        # 申诉改判：补一条恢复，原来那条不动
        _record(db, t.executor_id, t.category, "restore", -slash.points, "dispute", d.id, "申诉改判，恢复此前的罚没")
        for v in db.query(InfluenceVouch).filter(InfluenceVouch.dispute_id == d.id, InfluenceVouch.status == "slashed"):
            lost_stake = db.query(InfluenceEvent.points).filter(
                InfluenceEvent.user_id == v.voucher_id, InfluenceEvent.kind == "slash_vouch",
                InfluenceEvent.ref_type == "vouch", InfluenceEvent.ref_id == v.id).scalar() or 0.0
            _record(db, v.voucher_id, v.category, "restore", -lost_stake, "vouch", v.id,
                    "你担保的人申诉改判，恢复此前罚没的担保额")
            v.status = "released"
            db.add(v)
        # 改判后执行方拿到过半：这一单照常算挣（幂等，之前没记过才记）
        if t.status == "completed":
            on_task_completed(db, {"task_id": t.id})


# ------------------------------------------------------------------ 读：有效影响力与等级（INF-102 / 104）
def _rating_points(db: Session, user_ids: list[int], category: str | None, now: datetime) -> dict[tuple[int, str], float]:
    """已揭晓的评价：每颗星偏离 3 星 2 点（5 星 +4，1 星 −4），按评价时间衰减。"""
    from app.modules.task.models import Review, Task

    q = (db.query(Review.target_id, Task.category, Review.stars, Review.created_at)
         .join(Task, Task.id == Review.task_id)
         .filter(Review.target_id.in_(user_ids or [-1]), Review.rating_applied.is_(True),
                 Task.executor_id == Review.target_id))
    if category is not None:
        q = q.filter(Task.category == category)
    out: dict[tuple[int, str], float] = defaultdict(float)
    for uid, cat, stars, at in q:
        out[(uid, cat)] += decay((stars - 3) * 2, at, now)
    return out


def ledger(db: Session, user_ids: list[int], category: str | None = None, now: datetime | None = None
           ) -> dict[tuple[int, str], float]:
    """(人, 类目) → 当前有效影响力（衰减后，含已揭晓评价）。两条查询，与人数无关。"""
    now = now or utcnow()
    q = db.query(InfluenceEvent.user_id, InfluenceEvent.category, InfluenceEvent.points, InfluenceEvent.created_at)\
        .filter(InfluenceEvent.user_id.in_(user_ids or [-1]))
    if category is not None:
        q = q.filter(InfluenceEvent.category == category)
    out: dict[tuple[int, str], float] = defaultdict(float)
    for uid, cat, pts, at in q:
        out[(uid, cat)] += decay(pts, at, now)
    for k, v in _rating_points(db, user_ids, category, now).items():
        out[k] += v
    return {k: max(round(v, 1), 0.0) for k, v in out.items()}


def effective(db: Session, user_ids: list[int], category: str) -> dict[int, float]:
    return {uid: v for (uid, _), v in ledger(db, user_ids, category).items()}


def locked(db: Session, user_id: int, category: str) -> float:
    return float(db.query(func.coalesce(func.sum(InfluenceVouch.stake), 0.0))
                 .filter(InfluenceVouch.voucher_id == user_id, InfluenceVouch.category == category,
                         InfluenceVouch.status == "active").scalar() or 0.0)


def category_stats(db: Session, user_ids: list[int], category: str | None = None) -> dict[tuple[int, str], dict]:
    """(人, 类目) → 完成单数、平均星级、最近一次被罚的时间。"""
    from app.modules.task.models import Review, Task

    out: dict[tuple[int, str], dict] = defaultdict(lambda: {"completed": 0, "stars": [], "last_slash": None})
    q = db.query(Task.executor_id, Task.category, Task.id).filter(Task.executor_id.in_(user_ids or [-1]),
                                                                  Task.status == "completed")
    if category is not None:
        q = q.filter(Task.category == category)
    rows = q.all()
    for uid, cat, _ in rows:
        out[(uid, cat)]["completed"] += 1
    rq = (db.query(Review.target_id, Task.category, Review.stars).join(Task, Task.id == Review.task_id)
          .filter(Review.target_id.in_(user_ids or [-1]), Review.rating_applied.is_(True), Task.executor_id == Review.target_id))
    if category is not None:
        rq = rq.filter(Task.category == category)
    for uid, cat, stars in rq:
        out[(uid, cat)]["stars"].append(stars)
    sq = db.query(InfluenceEvent.user_id, InfluenceEvent.category, func.max(InfluenceEvent.created_at))\
        .filter(InfluenceEvent.user_id.in_(user_ids or [-1]), InfluenceEvent.kind == "slash_dispute")\
        .group_by(InfluenceEvent.user_id, InfluenceEvent.category)
    for uid, cat, at in sq:
        out[(uid, cat)]["last_slash"] = at
    return out


def tier(points: float, stats: dict, verified: bool, now: datetime | None = None) -> tuple[str, list[str]]:
    """返回（等级, 离下一级还差什么）。专家及以上要求实名、星级与「近期没有被罚」。"""
    now = now or utcnow()
    stars = stats.get("stars") or []
    avg = sum(stars) / len(stars) if stars else None
    last_slash = stats.get("last_slash")
    reached = "newcomer"
    for key, _name, need, n, min_avg, clean_days in reversed(TIERS):
        ok = points >= need and stats.get("completed", 0) >= n
        if min_avg is not None:
            ok = ok and verified and avg is not None and avg >= min_avg
        if clean_days is not None and last_slash is not None:
            ok = ok and last_slash < now - timedelta(days=clean_days)
        if ok:
            reached = key
    gaps: list[str] = []
    idx = [k for k, *_ in TIERS].index(reached)
    if idx > 0:
        key, name, need, n, min_avg, clean_days = TIERS[idx - 1]
        if points < need:
            gaps.append(f"影响力还差 {need - points:.0f} 点")
        if stats.get("completed", 0) < n:
            gaps.append(f"还要再完成 {n - stats.get('completed', 0)} 单")
        if min_avg is not None and (avg is None or avg < min_avg):
            gaps.append(f"平均星级要到 {min_avg}")
        if min_avg is not None and not verified:
            gaps.append("要先完成实名")
        if clean_days is not None and last_slash is not None and last_slash >= now - timedelta(days=clean_days):
            gaps.append(f"近 {clean_days} 天内不能有纠纷败诉")
        gaps = [f"升到「{name}」：" + "；".join(gaps)] if gaps else []
    return reached, gaps


def tiers_for(db: Session, users: list, category: str) -> dict[int, str]:
    """撮合用：一批候选人在这个类目的等级（几条查询，与人数无关）。"""
    ids = [u.id for u in users]
    pts = effective(db, ids, category)
    stats = category_stats(db, ids, category)
    return {u.id: tier(pts.get(u.id, 0.0), stats.get((u.id, category), {}), bool(u.is_verified))[0] for u in users}


# ------------------------------------------------------------------ 快照与 Merkle 证明（INF-106）
def leaf(user_id: int, category: str, points: float) -> str:
    return hashlib.sha256(json.dumps([user_id, category, points], ensure_ascii=False).encode()).hexdigest()


def _parent(a: str, b: str) -> str:
    lo, hi = sorted((a, b))
    return hashlib.sha256((lo + hi).encode()).hexdigest()


def merkle(leaves: list[str]) -> tuple[str, list[list[str]]]:
    """排序后的叶子建树；返回根与每一层（证明用）。奇数个时最后一个与自己配对。"""
    level = sorted(leaves) or [hashlib.sha256(b"").hexdigest()]
    levels = [level]
    while len(level) > 1:
        if len(level) % 2:
            level = level + [level[-1]]
        level = [_parent(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        levels.append(level)
    return level[0], levels


def proof(levels: list[list[str]], target: str) -> list[str]:
    path, h = [], target
    for level in levels[:-1]:
        lv = level + [level[-1]] if len(level) % 2 else level
        i = lv.index(h)
        sib = lv[i + 1] if i % 2 == 0 else lv[i - 1]
        path.append(sib)
        h = _parent(h, sib)
    return path


def verify_proof(target: str, path: list[str], root: str) -> bool:
    h = target
    for sib in path:
        h = _parent(h, sib)
    return h == root


def snapshot_values(db: Session, now: datetime | None = None) -> dict[tuple[int, str], float]:
    ids = [uid for (uid,) in db.query(InfluenceEvent.user_id).distinct()]
    return {k: v for k, v in ledger(db, ids, None, now).items() if v > 0}


def take_snapshot(db: Session) -> InfluenceSnapshot:
    from app.core.timefmt import iso
    from app.modules.anchor.service import anchor

    now = utcnow()
    values = snapshot_values(db, now)
    root, _ = merkle([leaf(u, c, v) for (u, c), v in values.items()])
    # 叶子原样存下：之后的证明必须用快照那一刻的数（影响力每天都在衰减）
    snap = InfluenceSnapshot(taken_at=now, merkle_root=root, leaves=len(values),
                             entries=sorted([u, c, v] for (u, c), v in values.items()))
    db.add(snap)
    db.flush()
    entry = anchor(db, "influence.snapshot", "influence", snap.id,
                   {"merkle_root": root, "leaves": len(values), "taken_at": iso(now)})
    snap.anchor_seq = entry.seq
    db.add(snap)
    return snap


def register_event_handlers() -> None:
    from app.core.events import subscribe

    subscribe("task.completed", on_task_completed, retry=True)
    subscribe("dispute.resolved", on_dispute_resolved, retry=True)
