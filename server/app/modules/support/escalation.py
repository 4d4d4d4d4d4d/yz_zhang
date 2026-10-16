"""ESCA-051 客服工单超时自动升级（150 号 spec）。

V101 起超过 SLA 的工单会进「人审队列积压」那条汇总通知——发给**全体管理员**，一天一条，
谁都收到等于谁都没被点名。工单本身不知道自己超时了，接手的客服也不会被单独叫醒。

这里按级别逐级叫人，只在平台内部（不转纠纷、不动钱——那仍然留给人决定）：
- 第 1 级（等了 `SUPPORT_SLA_HOURS`）：叫醒接手的客服；没人接手就叫醒全体客服；
- 第 2 级（等了 `SUPPORT_ESCALATE_L2_HOURS`）：叫醒超级管理员（主管），并告诉提单人「已升级给主管」。
级别写在工单上，每一级只叫一次；认领不重置计时（我们承诺的是多久解决，而不是多久有人认领）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.admin_roles import has_role, roles_of
from app.core.config import settings
from app.modules.account.models import User, utcnow

from .models import Ticket

LEVEL_LABEL = {0: "", 1: "已叫醒客服", 2: "已升级给主管"}


CATEGORIES = {"funds": "资金（提现、退款、到账）", "account": "账号（登录、安全）", "general": "一般"}
URGENT_CATEGORIES = ("funds", "account")
PRIORITY_LABEL = {"urgent": "加急", "normal": "一般"}


def thresholds(t: Ticket | None = None) -> tuple[int, int]:
    """处理时限与升级主管的时限。ESCA-052 加急工单用更短的一组。"""
    if t is not None and t.priority == "urgent":
        l1 = settings.SUPPORT_URGENT_SLA_HOURS
        return l1, max(l1, settings.SUPPORT_URGENT_ESCALATE_L2_HOURS)
    l1 = settings.SUPPORT_SLA_HOURS
    return l1, max(l1, settings.SUPPORT_ESCALATE_L2_HOURS)


def first_response_limit(t: Ticket | None = None) -> int:
    if t is not None and t.priority == "urgent":
        return settings.SUPPORT_URGENT_FIRST_RESPONSE_HOURS
    return settings.SUPPORT_FIRST_RESPONSE_HOURS


def waited_hours(t: Ticket, now: datetime | None = None) -> int:
    return int(((now or utcnow()) - t.created_at).total_seconds() // 3600)


def due_level(t: Ticket, now: datetime | None = None) -> int:
    """按等了多久，这张工单此刻应该在第几级。已结单的不升级。"""
    if t.status != "open":
        return 0
    l1, l2 = thresholds(t)
    w = ((now or utcnow()) - t.created_at).total_seconds()
    return 2 if w >= l2 * 3600 else 1 if w >= l1 * 3600 else 0


def first_response_overdue(t: Ticket, now: datetime | None = None) -> bool:
    """ESCA-053 还开着、客服一句话都没回、且已经等过首次响应时限。"""
    if t.status != "open" or t.first_response_at is not None:
        return False
    return ((now or utcnow()) - t.created_at).total_seconds() >= first_response_limit(t) * 3600


def sla_view(t: Ticket, now: datetime | None = None) -> dict:
    """列表与详情共用：等了多久、承诺多久、超了多久、升到第几级。时间差在服务端算好，客户端不自己解析时间。
    ESCA-053（157 号 spec）起多首次响应：有没有人回过第一句话、首次响应时限、是否已超。"""
    w = waited_hours(t, now)
    sla = thresholds(t)[0]
    return {"escalation_level": t.escalation_level or 0, "escalation_label": LEVEL_LABEL.get(t.escalation_level or 0, ""),
            "waited_hours": w, "sla_hours": sla,
            "overdue_hours": max(0, w - sla) if t.status == "open" else 0,
            "first_responded": t.first_response_at is not None,
            "first_response_hours": first_response_limit(t),
            "first_response_overdue": first_response_overdue(t, now),
            # ESCA-052（172 号 spec）
            "category": t.category or "general", "priority": t.priority or "normal",
            "priority_label": PRIORITY_LABEL.get(t.priority or "normal", "一般")}


def record_staff_reply(db: Session, t: Ticket, admin_id: int, body: str) -> None:
    """ESCA-053 客服的一次回复：记进往来、更新最近一次回复（兼容 `Ticket.reply`）、第一次回复记下首次响应时间。"""
    from .models import TicketReply

    now = utcnow()
    db.add(TicketReply(ticket_id=t.id, author_id=admin_id, is_staff=True, body=body, created_at=now))
    t.reply = body
    if t.first_response_at is None:
        t.first_response_at = now


def _admins(db: Session) -> list[User]:
    return db.query(User).filter(User.is_admin.is_(True), User.is_banned.is_(False)).order_by(User.id).all()


def level1_recipients(db: Session, t: Ticket) -> list[int]:
    if t.assignee_id:
        u = db.get(User, t.assignee_id)
        if u and u.is_admin and not u.is_banned and has_role(u, "support"):
            return [u.id]
    admins = _admins(db)
    support = [u.id for u in admins if "support" in roles_of(u)]
    # 没有专职客服时退到「能处理工单的人」（超级管理员）
    return support or [u.id for u in admins if has_role(u, "support")]


def level2_recipients(db: Session) -> list[int]:
    admins = _admins(db)
    return [u.id for u in admins if "super" in roles_of(u)] or [u.id for u in admins]


def escalate_overdue(db: Session, now: datetime | None = None) -> dict:
    from app.modules.notification.service import notify

    now = now or utcnow()
    out = {"level1": [], "level2": [], "notified": 0, "submitters_told": 0, "first_response_alerts": []}
    for t in db.query(Ticket).filter(Ticket.status == "open").order_by(Ticket.id).all():
        # ESCA-053 首次响应超时：叫醒接手人（没人接手叫醒客服），只叫一次；与解决时限的分级各算各的
        if first_response_overdue(t, now) and t.first_response_alerted_at is None:
            for uid in level1_recipients(db, t):
                notify(db, uid, "system", "工单首次响应超时",
                       f"工单 #{t.id}「{t.subject[:40]}」已等 {waited_hours(t, now)} 小时还没有客服回过一句话"
                       f"（首次响应时限 {first_response_limit(t)} 小时）。先回一句告诉对方在处理，不必等到能结单。")
                out["notified"] += 1
            t.first_response_alerted_at = now
            out["first_response_alerts"].append(t.id)
        target = due_level(t, now)
        if target <= (t.escalation_level or 0):
            continue
        l1h, l2h = thresholds(t)
        w = waited_hours(t, now)
        who = ""
        if t.assignee_id:
            a = db.get(User, t.assignee_id)
            who = f"，接手人 {a.nickname if a else '#' + str(t.assignee_id)}"
        # 跳级（例如调度停了两天）时两级都叫：客服和主管都该知道
        if (t.escalation_level or 0) < 1:
            for uid in level1_recipients(db, t):
                notify(db, uid, "system", "工单超时：请尽快处理",
                       f"工单 #{t.id}「{t.subject[:40]}」已等待 {w} 小时，超过承诺的 {l1h} 小时{who}。"
                       f"到管理后台「待处理工单」回复并结单；处理不了请认领后转给能处理的人。")
                out["notified"] += 1
            out["level1"].append(t.id)
        if target >= 2:
            for uid in level2_recipients(db):
                notify(db, uid, "system", "工单升级：需要主管介入",
                       f"工单 #{t.id}「{t.subject[:40]}」已等待 {w} 小时（{l2h} 小时升级线）{who or '，至今无人接手'}。"
                       f"请指派客服或亲自处理。")
                out["notified"] += 1
            notify(db, t.user_id, "system", "你的工单已升级给主管",
                   f"「{t.subject[:40]}」等待超过 {l2h} 小时，我们已升级给客服主管跟进。很抱歉让你久等。")
            out["submitters_told"] += 1
            out["level2"].append(t.id)
        t.escalation_level, t.escalated_at = target, now
    return out
