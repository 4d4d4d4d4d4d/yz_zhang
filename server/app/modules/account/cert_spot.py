"""CERT-053（348 号 spec）资质审核抽检。

资质一核准就生效，准入只看审核员一个人的判断：放水只能事后翻审计日志。这里加第二双眼：

- 核准时抽检：和人身安全、未成年人有关的资质（驾驶证、无犯罪记录、电工、高处作业、开锁、护理员）全部抽；
  其他按 10% 抽。抽不抽由服务端按申请编号与平台密钥算出（同一份申请结果固定，审核员事先猜不到）。
- 抽到的给另一位合规审核员复看：维持就结束；推翻要写理由，资质立刻撤销、通知持证人、进审计。
- 原审核员不能复看自己审的。每位审核员被抽了多少、被推翻多少，列表里一起给出。
- 抽检不拦已生效的资质（准入照常），只是事后复核。
- CERT-054（350 号 spec）审核员分级：新审核员（核准不满 20 份）的核准全部抽；复看过至少 5 份、被推翻两成以上的
  审核员列入「重点看」，抽检比例提到五成。新人和放水多的人最需要第二双眼。
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.admin_roles import require_role
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.core.timefmt import iso

from .models import User, utcnow
from .models_cert import CertificationApplication, CertSpotCheck

router = APIRouter(tags=["admin"])

SPOT_CHECK_RATE = 0.1
NEW_REVIEWER_APPROVALS = 20     # CERT-054 核准不满这么多份的算新审核员，全抽
WATCH_MIN_CHECKED = 5           # 复看过至少这么多份才算推翻率
WATCH_OVERTURN_RATE = 0.2       # 推翻率到这个数列入「重点看」
WATCH_SPOT_RATE = 0.5


def high_risk_certs() -> set[str]:
    from app.modules.task import service as ts

    return {ts.MINOR_CARE_CERT, ts.DRIVER_CERT, ts.CAREGIVER_CERT, ts.ELECTRICIAN_CERT, ts.HEIGHT_WORK_CERT, ts.LOCKSMITH_CERT}


def _sampled(application_id: int, rate: float | None = None) -> bool:
    h = hashlib.sha256(f"{settings.JWT_SECRET}:cert-spot:{application_id}".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2 ** 32 < (SPOT_CHECK_RATE if rate is None else rate)


def reviewer_grade(db: Session, reviewer_id: int) -> str:
    """CERT-054 new（核准不满 20 份）/ watch（复看过 ≥5 份、被推翻 ≥20%）/ normal。

    核准份数按审计记录数（撤销会改写申请上的 decided_by，审计不会）；核准当下这一份的审计还没写，所以抽检时
    数的是「之前」的份数：第 1~20 份都算新人。"""
    from app.modules.admin.models import AdminAudit

    approvals = (db.query(AdminAudit.id)
                 .filter(AdminAudit.admin_id == reviewer_id, AdminAudit.action == "certification_decide",
                         AdminAudit.detail.like("通过%")).count())
    if approvals < NEW_REVIEWER_APPROVALS:
        return "new"
    checked = (db.query(CertSpotCheck.status)
               .filter(CertSpotCheck.reviewer_id == reviewer_id, CertSpotCheck.status != "pending").all())
    over = sum(1 for (st,) in checked if st == "overturned")
    if len(checked) >= WATCH_MIN_CHECKED and over >= len(checked) * WATCH_OVERTURN_RATE:
        return "watch"
    return "normal"


def maybe_sample(db: Session, row: CertificationApplication) -> CertSpotCheck | None:
    """核准后调用：高风险资质全抽，其他按比例抽。已经抽过的不重复。"""
    if row.status != "approved" or row.decided_by is None:
        return None
    if row.name in high_risk_certs():
        reason = "high_risk"
    else:
        grade = reviewer_grade(db, row.decided_by)
        reason = ("new_reviewer" if grade == "new" else "watch" if grade == "watch" and _sampled(row.id, WATCH_SPOT_RATE)
                  else "random" if _sampled(row.id) else "")
    if not reason or db.query(CertSpotCheck.id).filter(CertSpotCheck.application_id == row.id).first():
        return None
    s = CertSpotCheck(application_id=row.id, user_id=row.user_id, name=row.name, reviewer_id=row.decided_by,
                      reason=reason, status="pending", note="")
    db.add(s)
    db.flush()
    return s


def spot_row(s: CertSpotCheck, names: dict[int, str]) -> dict:
    return {"id": s.id, "application_id": s.application_id, "user_id": s.user_id, "name": s.name,
            "reviewer_id": s.reviewer_id, "reviewer_nickname": names.get(s.reviewer_id, ""),
            "reason": s.reason, "status": s.status, "checked_by": s.checked_by, "note": s.note,
            "created_at": iso(s.created_at), "checked_at": iso(s.checked_at) if s.checked_at else None}


@router.get("/admin/cert-spot-checks")
def list_spot_checks(status: str = Query(default="pending", pattern="^(pending|confirmed|overturned|all)$"),
                     admin: User = Depends(require_role("compliance")), db: Session = Depends(get_db, scope="function")):
    q = db.query(CertSpotCheck)
    if status != "all":
        q = q.filter(CertSpotCheck.status == status)
    rows = q.order_by(CertSpotCheck.id if status == "pending" else CertSpotCheck.id.desc()).limit(200).all()
    every = db.query(CertSpotCheck.reviewer_id, CertSpotCheck.status).all()
    stats: dict[int, dict] = {}
    for rid, st in every:
        x = stats.setdefault(rid, {"sampled": 0, "overturned": 0})
        x["sampled"] += 1
        x["overturned"] += st == "overturned"
    ids = {r.reviewer_id for r in rows} | set(stats)
    names = {u.id: u.nickname for u in db.query(User).filter(User.id.in_(ids or [-1]))}
    return {"items": [spot_row(r, names) for r in rows],
            "reviewers": [{"reviewer_id": rid, "nickname": names.get(rid, ""), **x, "grade": reviewer_grade(db, rid)}
                          for rid, x in sorted(stats.items(), key=lambda kv: (-kv[1]["overturned"], kv[0]))]}


class SpotVerdictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(default="", max_length=300)


def _pending(db: Session, spot_id: int, admin: User) -> CertSpotCheck:
    s = db.get(CertSpotCheck, spot_id)
    if s is None:
        raise not_found("没有这条抽检")
    if s.reviewer_id == admin.id:
        raise forbidden("不能复看自己审的资质，请另一位审核员复看", "cert_spot_self")
    if s.status != "pending":
        raise conflict("这条抽检已经复看过了", "cert_spot_decided")
    return s


@router.post("/admin/cert-spot-checks/{spot_id}/confirm")
def confirm_spot_check(spot_id: int, body: SpotVerdictIn, admin: User = Depends(require_role("compliance")),
                       db: Session = Depends(get_db, scope="function")):
    from app.modules.admin.router import record_audit

    s = _pending(db, spot_id, admin)
    s.status, s.checked_by, s.checked_at, s.note = "confirmed", admin.id, utcnow(), body.note.strip()
    db.add(s)
    record_audit(db, admin.id, "cert_spot_confirm", "certification", s.application_id, f"抽检 #{s.id} 维持")
    db.flush()
    return spot_row(s, {})


@router.post("/admin/cert-spot-checks/{spot_id}/overturn")
def overturn_spot_check(spot_id: int, body: SpotVerdictIn, admin: User = Depends(require_role("compliance")),
                        db: Session = Depends(get_db, scope="function")):
    """推翻：资质立刻撤销（和人工撤销同一处）、通知持证人、进审计。"""
    from app.modules.account import cert_service
    from app.modules.admin.router import record_audit
    from app.modules.notification.service import notify

    note = body.note.strip()
    if len(note) < 4:
        raise bad_request("推翻要写理由（至少 4 个字）：持证人会看到这句话，原审核员也要知道错在哪", "cert_spot_reason_required")
    s = _pending(db, spot_id, admin)
    row = db.get(CertificationApplication, s.application_id)
    if row is not None and row.status == "approved":
        cert_service.revoke(db, row, admin, f"抽检复核不通过：{note}")
    s.status, s.checked_by, s.checked_at, s.note = "overturned", admin.id, utcnow(), note
    db.add(s)
    record_audit(db, admin.id, "cert_spot_overturn", "certification", s.application_id, f"抽检 #{s.id} 推翻：{note}")
    notify(db, s.user_id, "system", f"你的「{s.name}」资质复核没有通过",
           f"{note}。资质已撤销，可以补充材料后重新申请。")
    db.flush()
    return spot_row(s, {})
