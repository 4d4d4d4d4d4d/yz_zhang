from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_verified
from app.core.errors import bad_request, conflict, forbidden, not_found
from app.modules.account.models import User
from app.modules.contract import service as contract_service
from app.modules.task.models import Application, Task
from app.modules.task.service import transition

from .models import Invitation, Subscription

router = APIRouter(tags=["matching"])


class InviteIn(BaseModel):
    user_id: int
    message: str = ""


class SubscribeIn(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    city: str = ""


# ---------- MATCH-004 定向邀约 ----------
@router.post("/tasks/{task_id}/invitations", status_code=201)
def invite(
    task_id: int, body: InviteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    task = db.get(Task, task_id)
    if not task:
        raise not_found("任务不存在")
    if task.creator_id != user.id:
        raise forbidden("仅发布者可发出邀约")
    if task.status != "published":
        raise conflict("任务不在招募中", "not_recruiting")
    invitee = db.get(User, body.user_id)
    if not invitee or not invitee.is_verified:
        raise bad_request("被邀请人不存在或未实名", "invalid_invitee")
    if body.user_id == user.id:
        raise bad_request("不能邀请自己", "self_invite")
    if db.query(Invitation).filter(
        Invitation.task_id == task_id, Invitation.invitee_id == body.user_id
    ).first():
        raise conflict("已邀请过该用户", "already_invited")
    row = Invitation(task_id=task_id, inviter_id=user.id, invitee_id=body.user_id, message=body.message)
    db.add(row)
    db.flush()
    from app.modules.notification.service import notify

    notify(db, body.user_id, "task", "收到任务邀约", f"《{task.title}》邀请你接单，报酬 {task.budget_cents / 100:.2f} 元")
    return {"id": row.id, "status": row.status}


@router.get("/invitations")
def my_invitations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(Invitation)
        .filter(Invitation.invitee_id == user.id)
        .order_by(Invitation.id.desc())
        .limit(50)
        .all()
    )
    out = []
    for r in rows:
        task = db.get(Task, r.task_id)
        out.append(
            {"id": r.id, "task_id": r.task_id, "task_title": task.title if task else "",
             "budget_cents": task.budget_cents if task else 0, "message": r.message,
             "status": r.status, "task_status": task.status if task else ""}
        )
    return out


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(
    invitation_id: int, user: User = Depends(require_verified), db: Session = Depends(get_db)
):
    """接受邀约 = 直接成交：生成报名记录 + 合约，任务 → matched（TASK-020）。"""
    inv = db.get(Invitation, invitation_id)
    if not inv or inv.invitee_id != user.id:
        raise not_found("邀约不存在")
    if inv.status != "pending":
        raise conflict("邀约已处理", "invitation_closed")
    task = db.get(Task, inv.task_id)
    if task.status != "published":
        inv.status = "declined"
        db.add(inv)
        raise conflict("任务已不在招募中，邀约失效", "task_closed")
    inv.status = "accepted"
    app_row = Application(
        task_id=task.id, applicant_id=user.id, bid_cents=task.budget_cents,
        message=f"[邀约] {inv.message}", status="accepted",
    )
    task.executor_id = user.id
    db.add_all([inv, app_row, task])
    contract = contract_service.generate(db, task, user.id, task.budget_cents)
    transition(db, task, "matched", {"executor_id": user.id})
    return {"contract_id": contract.id, "task_id": task.id}


@router.post("/invitations/{invitation_id}/decline")
def decline_invitation(
    invitation_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    inv = db.get(Invitation, invitation_id)
    if not inv or inv.invitee_id != user.id:
        raise not_found("邀约不存在")
    if inv.status != "pending":
        raise conflict("邀约已处理", "invitation_closed")
    inv.status = "declined"
    db.add(inv)
    return {"status": "declined"}


# ---------- TASK-042 任务订阅 ----------
@router.post("/subscriptions", status_code=201)
def subscribe_category(
    body: SubscribeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if db.query(Subscription).filter(
        Subscription.user_id == user.id,
        Subscription.category == body.category,
        Subscription.city == body.city,
    ).first():
        raise conflict("已订阅", "already_subscribed")
    row = Subscription(user_id=user.id, category=body.category, city=body.city)
    db.add(row)
    db.flush()
    return {"id": row.id}


@router.get("/subscriptions")
def my_subscriptions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Subscription).filter(Subscription.user_id == user.id).all()
    return [{"id": r.id, "category": r.category, "city": r.city} for r in rows]


@router.delete("/subscriptions/{sub_id}")
def unsubscribe(sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Subscription, sub_id)
    if not row or row.user_id != user.id:
        raise not_found("订阅不存在")
    db.delete(row)
    return {"ok": True}
