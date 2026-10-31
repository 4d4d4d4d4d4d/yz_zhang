"""INF-100 影响力与专家等级接口（127 号 spec）。

没有任何「转让 / 赠送 / 兑换 / 提现」接口——影响力只能本人挣、本人被罚（闸门钉住）。
"""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.errors import bad_request, conflict, not_found
from app.core.locks import job_slot
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from . import service as svc
from .models import InfluenceEvent, InfluenceSnapshot, InfluenceVouch

router = APIRouter(tags=["influence"])
CATEGORY_VOUCH_DAYS = 180
WORK_STARTED = ("matched", "in_progress", "pending_acceptance", "disputed")


class VouchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: int
    category: str = Field(min_length=1, max_length=50)
    task_id: int | None = None
    stake: float = Field(gt=0, le=10000)
    note: str = Field(default="", max_length=200)


def _public_target(db: Session, user_id: int, viewer: User) -> User:
    u = db.get(User, user_id)
    if (u is None or u.is_deleted or u.is_banned
            or ((u.privacy or {}).get("profile_public") is False and u.id != viewer.id)):
        raise not_found("用户不存在")
    return u


def _dump_vouch(v: InfluenceVouch, names: dict[int, str]) -> dict:
    return {"id": v.id, "voucher_id": v.voucher_id, "voucher_nickname": names.get(v.voucher_id, ""),
            "subject_id": v.subject_id, "subject_nickname": names.get(v.subject_id, ""), "category": v.category,
            "task_id": v.task_id, "stake": v.stake, "status": v.status, "note": v.note,
            "created_at": iso(v.created_at), "resolved_at": iso(v.resolved_at)}


def _categories(db: Session, user: User, public: bool) -> list[dict]:
    ledger = svc.ledger(db, [user.id])
    stats = svc.category_stats(db, [user.id])
    cats = sorted({c for (_, c) in ledger} | {c for (_, c) in stats}, key=lambda c: -ledger.get((user.id, c), 0.0))
    out = []
    for c in cats:
        if not c:
            continue
        pts = ledger.get((user.id, c), 0.0)
        st = stats.get((user.id, c), {})
        key, gaps = svc.tier(pts, st, bool(user.is_verified))
        stars = st.get("stars") or []
        row = {"category": c, "points": round(pts), "tier": key, "tier_name": svc.TIER_NAMES[key],
               "completed": st.get("completed", 0), "rating_avg": round(sum(stars) / len(stars), 1) if stars else None}
        if not public:
            lk = svc.locked(db, user.id, c)
            row.update({"locked": round(lk, 1), "available": round(max(pts * svc.VOUCH_MAX_SHARE - lk, 0), 1), "gaps": gaps})
        out.append(row)
    return out


def _vouch_summary(db: Session, subject_id: int) -> list[dict]:
    rows = db.query(InfluenceVouch).filter(InfluenceVouch.subject_id == subject_id, InfluenceVouch.status == "active").all()
    by: dict[str, dict] = {}
    for v in rows:
        s = by.setdefault(v.category, {"category": v.category, "vouchers": 0, "stake": 0.0})
        s["vouchers"] += 1
        s["stake"] = round(s["stake"] + v.stake, 1)
    return sorted(by.values(), key=lambda x: -x["stake"])


# ------------------------------------------------------------------ 读
@router.get("/influence/me")
def my_influence(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    events = (db.query(InfluenceEvent).filter(InfluenceEvent.user_id == user.id)
              .order_by(InfluenceEvent.id.desc()).limit(30).all())
    given = db.query(InfluenceVouch).filter(InfluenceVouch.voucher_id == user.id).order_by(InfluenceVouch.id.desc()).limit(50).all()
    received = db.query(InfluenceVouch).filter(InfluenceVouch.subject_id == user.id).order_by(InfluenceVouch.id.desc()).limit(50).all()
    ids = {v.voucher_id for v in given + received} | {v.subject_id for v in given + received}
    names = {u.id: u.nickname for u in db.query(User).filter(User.id.in_(ids or {-1}))}
    return {
        "categories": _categories(db, user, public=False),
        "events": [{"id": e.id, "category": e.category, "kind": e.kind, "points": e.points, "reason": e.reason,
                    "created_at": iso(e.created_at)} for e in events],
        "vouches_given": [_dump_vouch(v, names) for v in given],
        "vouches_received": [_dump_vouch(v, names) for v in received],
        "rules": f"只能靠在平台上做成事挣；不能转让；按 {svc.HALF_LIFE_DAYS} 天半衰期衰减；纠纷败诉罚没当前的 30%；"
                 f"担保额合计不超过自己在该类目影响力的一半，对方败诉罚没担保额的一半",
    }


@router.get("/users/{user_id}/influence")
def user_influence(user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """对外：各类目的等级与大致影响力、有多少人为他担保。不给事件明细。"""
    target = _public_target(db, user_id, user)
    return {"user_id": target.id, "categories": _categories(db, target, public=True), "vouched": _vouch_summary(db, target.id)}


@router.get("/influence/leaderboard")
def leaderboard(category: str = Query(min_length=1, max_length=50), user: User = Depends(get_current_user),
                db: Session = Depends(get_db, scope="function")):
    """某类目熟手以上的人（只列资料公开的），按影响力排。"""
    ids = [uid for (uid,) in db.query(InfluenceEvent.user_id).filter(InfluenceEvent.category == category).distinct().limit(2000)]
    users = [u for u in db.query(User).filter(User.id.in_(ids or [-1]), User.is_deleted.is_(False), User.is_banned.is_(False))
             if (u.privacy or {}).get("profile_public") is not False]
    pts = svc.effective(db, [u.id for u in users], category)
    stats = svc.category_stats(db, [u.id for u in users], category)
    rows = []
    for u in users:
        key, _ = svc.tier(pts.get(u.id, 0.0), stats.get((u.id, category), {}), bool(u.is_verified))
        if svc.TIER_RANK[key] >= svc.TIER_RANK["skilled"]:
            rows.append({"user_id": u.id, "nickname": u.nickname, "tier": key, "tier_name": svc.TIER_NAMES[key],
                         "points": round(pts.get(u.id, 0.0)), "completed": stats.get((u.id, category), {}).get("completed", 0)})
    rows.sort(key=lambda r: (-svc.TIER_RANK[r["tier"]], -r["points"], r["user_id"]))
    return {"category": category, "items": rows[:20]}


# ------------------------------------------------------------------ 担保（INF-105）
@router.post("/influence/vouches", status_code=201)
def create_vouch(body: VouchIn, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    from app.modules.task.models import Application, Task

    if body.subject_id == user.id:
        raise bad_request("不能给自己担保", "influence_vouch_self")
    subject = db.get(User, body.subject_id)
    if subject is None or subject.is_deleted or subject.is_banned:
        raise not_found("用户不存在")
    pts = svc.effective(db, [user.id], body.category).get(user.id, 0.0)
    my_tier, _ = svc.tier(pts, svc.category_stats(db, [user.id], body.category).get((user.id, body.category), {}),
                          bool(user.is_verified))
    if svc.TIER_RANK[my_tier] < svc.TIER_RANK["skilled"]:
        raise conflict(f"在「{body.category}」做到熟手以上才能为别人担保", "influence_vouch_tier")
    room = pts * svc.VOUCH_MAX_SHARE - svc.locked(db, user.id, body.category)
    if body.stake > room + 1e-9:
        raise conflict(f"担保额超出可用额度（现在最多 {max(room, 0):.1f} 点）", "influence_stake_exceeds")
    if body.task_id is not None:
        t = db.get(Task, body.task_id)
        applied = t is not None and db.query(Application.id).filter(Application.task_id == t.id,
                                                                     Application.applicant_id == subject.id).first()
        if (t is None or t.category != body.category or t.status in ("completed", "cancelled", "draft")
                or not (applied or t.executor_id == subject.id)):
            raise conflict("这一单不在这个类目，或者他没有报名 / 承接这一单", "influence_vouch_task_mismatch")
    dup = db.query(InfluenceVouch.id).filter(InfluenceVouch.voucher_id == user.id, InfluenceVouch.subject_id == subject.id,
                                            InfluenceVouch.category == body.category, InfluenceVouch.status == "active",
                                            (InfluenceVouch.task_id == body.task_id) if body.task_id is not None
                                            else InfluenceVouch.task_id.is_(None)).first()
    if dup:
        raise conflict("你已经为他在这里担保过了", "influence_vouch_exists")
    v = InfluenceVouch(voucher_id=user.id, subject_id=subject.id, category=body.category, task_id=body.task_id,
                       stake=round(body.stake, 1), note=body.note.strip())
    db.add(v)
    db.flush()
    from app.modules.notification.service import notify

    notify(db, subject.id, "system", "有人为你担保",
           f"{user.nickname} 以 {v.stake:.0f} 点「{v.category}」影响力为你担保" + (f"（任务 #{v.task_id}）" if v.task_id else ""))
    return _dump_vouch(v, {user.id: user.nickname, subject.id: subject.nickname})


@router.delete("/influence/vouches/{vouch_id}")
def withdraw_vouch(vouch_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    from app.modules.task.models import Task

    v = db.get(InfluenceVouch, vouch_id)
    if v is None or v.voucher_id != user.id:
        raise not_found("担保不存在")
    if v.status != "active":
        raise conflict("这笔担保已经结束了", "influence_vouch_closed")
    if v.task_id is not None:
        t = db.get(Task, v.task_id)
        if t is not None and t.executor_id == v.subject_id and t.status in WORK_STARTED:
            raise conflict("他已经开工了，担保要等这一单结束才释放", "influence_vouch_locked")
    v.status, v.resolved_at = "withdrawn", utcnow()
    db.add(v)
    db.flush()
    return {"withdrawn": True}


# ------------------------------------------------------------------ 快照与证明（INF-106）
def _dump_snapshot(s: InfluenceSnapshot | None) -> dict | None:
    if s is None:
        return None
    return {"id": s.id, "taken_at": iso(s.taken_at), "merkle_root": s.merkle_root, "leaves": s.leaves,
            "anchor_seq": s.anchor_seq}


@router.get("/influence/snapshots/latest")
def latest_snapshot(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    return {"snapshot": _dump_snapshot(db.query(InfluenceSnapshot).order_by(InfluenceSnapshot.id.desc()).first())}


@router.get("/influence/me/proof")
def my_proof(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    """我在最近一次快照里的每一条（类目、影响力），附 Merkle 路径：任何人拿着锚定的根都能自己验。"""
    s = db.query(InfluenceSnapshot).order_by(InfluenceSnapshot.id.desc()).first()
    if s is None:
        return {"snapshot": None, "items": []}
    leaves = [svc.leaf(u, c, p) for u, c, p in s.entries or []]
    root, levels = svc.merkle(leaves)
    items = []
    for u, c, p in s.entries or []:
        if u == user.id:
            lf = svc.leaf(u, c, p)
            path = svc.proof(levels, lf)
            items.append({"category": c, "points": p, "leaf": lf, "path": path,
                          "verified": svc.verify_proof(lf, path, s.merkle_root)})
    return {"snapshot": _dump_snapshot(s), "items": items}


@router.post("/influence/jobs/snapshot")
def job_snapshot(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                 __=Depends(job_slot("influence_snapshot"), scope="function")):
    """每天一次：到期的类目担保释放（不奖励），然后做快照并锚定。"""
    cutoff = utcnow() - timedelta(days=CATEGORY_VOUCH_DAYS)
    expired = (db.query(InfluenceVouch).filter(InfluenceVouch.status == "active", InfluenceVouch.task_id.is_(None),
                                               InfluenceVouch.created_at < cutoff).all())
    for v in expired:
        v.status, v.resolved_at = "released", utcnow()
        db.add(v)
    snap = svc.take_snapshot(db)
    db.flush()
    return {"released": len(expired), "snapshot": _dump_snapshot(snap)}
