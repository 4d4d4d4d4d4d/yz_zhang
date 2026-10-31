"""SCN-219（336 号 spec）被发单拦截挡下时申请人工复核。

发单拦截（errand.py）只看文字、不调模型，会误拦：「代写」可能是写公众号、「号源」可能是自己排队。改写说明能绕过的
人会改写，改不过去的就只能放弃。这里给一条正路：写一句说明，运营在后台看原文与说明，通过就放行**这一段文字发一单**，
维持就写清理由。

- 只认同一个人、一字不差的同一段文字（指纹）：改了说明就是另一段文字，要重新判断。
- 通过只放行一单：发出去就记在那一单上，同一段文字再发第二单照拦。
- 处理过的同一段文字不能再申请（维持的要改写后再发，通过的直接发就行）；同时在等的最多 5 条。
- 运营不能处理自己提出的复核（运营自己发单也会被拦）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.admin_roles import require_role
from app.core.db import get_db
from app.core.deps import get_current_user, require_job_auth
from app.core.locks import job_slot
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from .errand import errand_fingerprint, restricted_errand
from .models import ErrandReview

router = APIRouter(tags=["task"])

MAX_PENDING = 5
REMIND_HOURS = 24   # SCN-220 在等超过这么久还没人处理，每天催一次运营
EXPLANATION_MIN = 6
KIND_LABEL = {
    "rx": "代开处方药", "resale": "倒卖号源门票", "learner": "无证陪练学车",
    "ghostwrite": "代写学位论文代考", "fake_review": "刷单虚假评价", "fake_traffic": "刷粉刷量买卖账号",
    "fake_inspection": "年检包过不上线", "voice_clone": "克隆他人声音",
    "odometer_fraud": "篡改里程表",
}


def _text(title: str, description: str) -> str:
    # 与两处发单拦截拼文字的写法一字不差，指纹才对得上
    return f"{title} {description}"


def reviewed_pass(db: Session, user_id: int, text: str, task_id: int | None) -> bool:
    """这段文字有没有运营通过、还没用掉（或已经记在这一单上）的复核。只读：真正发出去时由 bind_review 记账。"""
    return _usable(db, user_id, text, task_id) is not None


def _usable(db: Session, user_id: int, text: str, task_id: int | None) -> ErrandReview | None:
    rows = (db.query(ErrandReview)
            .filter(ErrandReview.user_id == user_id, ErrandReview.fingerprint == errand_fingerprint(text),
                    ErrandReview.status == "approved")
            .order_by(ErrandReview.id).all())
    return (next((r for r in rows if task_id is not None and r.task_id == task_id), None)
            or next((r for r in rows if r.task_id is None), None))


def bind_review(db: Session, user_id: int, text: str, task_id: int) -> None:
    """这一单发出去了：如果它是靠复核放行的，把复核记在这一单上（放行一单）。没被拦的文字什么都不做。"""
    if restricted_errand(text) is None:
        return
    r = _usable(db, user_id, text, task_id)
    if r is not None and r.task_id is None:
        r.task_id = task_id
        db.add(r)
        db.flush()


def review_row(r: ErrandReview) -> dict:
    return {
        "id": r.id, "kind": r.kind, "kind_label": KIND_LABEL.get(r.kind, r.kind),
        "title": r.title, "description": r.description, "explanation": r.explanation,
        "status": r.status, "decision_note": r.decision_note, "task_id": r.task_id,
        "created_at": iso(r.created_at), "decided_at": iso(r.decided_at) if r.decided_at else None,
    }


class ErrandReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=5000)
    explanation: str = Field(max_length=300)


@router.post("/tasks/errand-reviews")
def request_errand_review(body: ErrandReviewIn, user: User = Depends(get_current_user),
                          db: Session = Depends(get_db, scope="function")):
    explanation = body.explanation.strip()
    if len(explanation) < EXPLANATION_MIN:
        raise bad_request(f"请写一句说明（至少 {EXPLANATION_MIN} 个字）：你要办的到底是什么事、为什么不是被拦的那一类。"
                          "运营只看这句话和原文来判断", "errand_review_explanation_required")
    text = _text(body.title, body.description)
    kind = restricted_errand(text)
    if kind is None:
        raise bad_request("这段文字现在没有被发单拦截挡下，可以直接发布，不用申请复核", "errand_review_not_blocked")
    fp = errand_fingerprint(text)
    same = (db.query(ErrandReview).filter(ErrandReview.user_id == user.id, ErrandReview.fingerprint == fp)
            .order_by(ErrandReview.id.desc()).all())
    latest = same[0] if same else None   # 同一段文字只看最近一条：在等、通过没用、维持都不能再申请
    if latest is not None and latest.status == "pending":
        raise conflict("这段文字已经在等运营复核了，有结果会通知你", "errand_review_pending")
    if latest is not None and latest.status == "approved" and latest.task_id is None:
        raise conflict("这段文字已经复核通过了，直接发布就行（放行一单）", "errand_review_approved")
    if latest is not None and latest.status == "rejected":
        raise conflict(f"这段文字复核过、没有通过：{latest.decision_note}。请按理由改写后再发；"
                       "改写后仍被拦的，可以再申请", "errand_review_rejected")
    pending = db.query(ErrandReview).filter(ErrandReview.user_id == user.id, ErrandReview.status == "pending").count()
    if pending >= MAX_PENDING:
        raise conflict(f"你同时在等的复核已经有 {MAX_PENDING} 条了，等出结果再申请", "errand_review_too_many")
    r = ErrandReview(user_id=user.id, kind=kind, title=body.title, description=body.description, fingerprint=fp,
                     explanation=explanation, status="pending", decision_note="")
    db.add(r)
    db.flush()
    from app.modules.openapi.router import _notify_ops

    _notify_ops(db, "有一条发单拦截的复核申请",
                f"复核 #{r.id}（{KIND_LABEL.get(kind, kind)}）：{body.title[:40]}。请到后台「发单复核」处理。")
    return review_row(r)


@router.get("/tasks/errand-reviews")
def my_errand_reviews(user: User = Depends(get_current_user), db: Session = Depends(get_db, scope="function")):
    rows = (db.query(ErrandReview).filter(ErrandReview.user_id == user.id)
            .order_by(ErrandReview.id.desc()).limit(50).all())
    return [review_row(r) for r in rows]


# ---------- 运营 ----------
class ErrandDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=300)


@router.get("/admin/errand-reviews")
def admin_errand_reviews(status: str = Query(default="pending", pattern="^(pending|approved|rejected|all)$"),
                         admin: User = Depends(require_role("ops")), db: Session = Depends(get_db, scope="function")):
    q = db.query(ErrandReview)
    if status != "all":
        q = q.filter(ErrandReview.status == status)
    rows = q.order_by(ErrandReview.id if status == "pending" else ErrandReview.id.desc()).limit(200).all()
    names = {u.id: u.nickname for u in db.query(User).filter(User.id.in_([r.user_id for r in rows] or [-1]))}
    now = utcnow()
    out = []
    for r in rows:
        waited = int(((r.decided_at or now) - r.created_at).total_seconds() // 3600)
        # SCN-220 写明时限，超过的标出来（已处理的按处理时算）
        out.append({**review_row(r), "user_id": r.user_id, "nickname": names.get(r.user_id, ""), "waited_hours": waited,
                    "sla_hours": REMIND_HOURS, "overdue": r.status == "pending" and waited >= REMIND_HOURS})
    return out


def remind_errand_reviews(db: Session) -> dict:
    """SCN-220（338 号 spec）在等超过 24 小时的发单复核催运营：每条一天最多一次，处理了就不再催。
    申请了没人看，等于没有这条路——发单人那一单一直发不出去。"""
    from datetime import timedelta

    from app.modules.openapi.router import _notify_ops

    now = utcnow()
    due = (db.query(ErrandReview)
           .filter(ErrandReview.status == "pending", ErrandReview.created_at <= now - timedelta(hours=REMIND_HOURS))
           .order_by(ErrandReview.id).all())
    due = [r for r in due if r.reminded_at is None or r.reminded_at <= now - timedelta(hours=24)]
    if not due:
        return {"reminded": 0}
    longest = max(int((now - r.created_at).total_seconds() // 3600) for r in due)
    _notify_ops(db, "发单复核等待处理",
                f"有 {len(due)} 条发单复核等了 {REMIND_HOURS} 小时以上还没处理（最久 {longest} 小时）："
                + "、".join(f"#{r.id}" for r in due[:10]) + "。发单人的单一直发不出去，请到后台「发单复核」通过或维持。")
    for r in due:
        r.reminded_at = now
        db.add(r)
    return {"reminded": len(due)}


@router.post("/tasks/jobs/remind-errand-reviews")
def run_remind_errand_reviews(db: Session = Depends(get_db, scope="function"), _=Depends(require_job_auth),
                              __=Depends(job_slot("errand_review_reminders"), scope="function")):
    """SCN-220 在等太久的发单复核催运营。"""
    return remind_errand_reviews(db)


def _pending(db: Session, review_id: int, admin: User) -> ErrandReview:
    r = db.get(ErrandReview, review_id)
    if r is None:
        raise not_found("没有这条复核")
    if r.user_id == admin.id:
        raise forbidden("不能处理自己提出的复核，请另一位运营处理", "errand_review_self")
    if r.status != "pending":
        raise conflict("这条复核已经处理过了", "errand_review_decided")
    return r


@router.post("/admin/errand-reviews/{review_id}/approve")
def approve_errand_review(review_id: int, body: ErrandDecisionIn, admin: User = Depends(require_role("ops")),
                          db: Session = Depends(get_db, scope="function")):
    from app.modules.admin.router import record_audit
    from app.modules.notification.service import notify

    r = _pending(db, review_id, admin)
    note = body.note.strip()
    r.status, r.decided_by, r.decided_at, r.decision_note = "approved", admin.id, utcnow(), note
    db.add(r)
    record_audit(db, admin.id, "errand_review_approve", "user", r.user_id,
                 f"复核 #{r.id}（{r.kind}）放行一单" + (f"：{note}" if note else ""))
    notify(db, r.user_id, "system", "你的发单复核通过了",
           f"复核 #{r.id}「{r.title[:40]}」：可以发布了（这段文字放行一单，改了文字要重新判断）。" + (f"运营说明：{note}" if note else ""))
    db.flush()
    return review_row(r)


@router.post("/admin/errand-reviews/{review_id}/reject")
def reject_errand_review(review_id: int, body: ErrandDecisionIn, admin: User = Depends(require_role("ops")),
                         db: Session = Depends(get_db, scope="function")):
    from app.modules.admin.router import record_audit
    from app.modules.notification.service import notify

    note = body.note.strip()
    if len(note) < 4:
        raise bad_request("维持拦截要写理由（至少 4 个字）：对方会看到这句话", "errand_review_reason_required")
    r = _pending(db, review_id, admin)
    r.status, r.decided_by, r.decided_at, r.decision_note = "rejected", admin.id, utcnow(), note
    db.add(r)
    record_audit(db, admin.id, "errand_review_reject", "user", r.user_id, f"复核 #{r.id}（{r.kind}）维持：{note}")
    notify(db, r.user_id, "system", "你的发单复核没有通过",
           f"复核 #{r.id}「{r.title[:40]}」：{note}。可以按理由改写后再发。")
    db.flush()
    return review_row(r)
