"""RISK-010~015（399 号 spec，V426）举报：类型、对象核对、不重复、每日上限、处理结果回给举报人。

为什么要补：举报接口（RISK-007）早就有，但
- 两端只有 App 的任务详情能举报；Web 上普通用户找不到任何举报入口，内容、个人空间、私信都举报不了；
- 举报人提交以后再也看不到结果；
- 不核对对象：举报一个不存在的 id 也进队列；同一个人对同一个对象能连点几十次，把审核队列冲掉。

《网络信息内容生态治理规定》第十六条要求平台设置便捷的投诉举报入口，及时受理处置并反馈处理结果。
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import bad_request, not_found, too_many_requests
from app.core.timefmt import iso
from app.modules.account.models import User, utcnow

from .models import Report

# 类型的说法给举报人看，也给审核员先分轻重；顺序就是两端下拉框的顺序
REPORT_CATEGORIES: dict[str, str] = {
    "illegal": "违法违规",
    "porn": "色情低俗",
    "fraud": "诈骗或骗钱",
    "harassment": "骚扰或辱骂",
    "infringement": "侵犯权益（抄袭、冒用、泄露隐私）",
    "other": "其他",
}

TARGET_LABELS = {"task": "任务", "content": "内容", "user": "用户", "message": "私信"}

# 回给举报人的处理结果：只说结果，不说是哪位审核员、不说对方被怎么处罚的细节
RESULT_LABELS = {
    "dismiss": "经核查没有发现违规，暂不处理",
    "remove_content": "已下架违规内容",
    "ban_user": "已处理违规账号",
}

# RISK-016（401 号 spec，V428）违法、诈骗、色情先处理：这三类拖一天就可能有人受骗或扩散。
# 处理时限：这三类 24 小时，其余 72 小时。时限是内部承诺，超了在队列里标红，不对外承诺
URGENT_CATEGORIES = ("illegal", "fraud", "porn")
SLA_HOURS = {"urgent": 24, "normal": 72}

# 一个人一天最多举报这么多次：正常用户一天举报十次以上极少见，再多就是在刷队列
DAILY_LIMIT = 20


def check_target(db: Session, user: User, target_type: str, target_id: int) -> None:
    """对象要存在、举报人看得到它、不是自己的（RISK-011）。

    私信只有会话里的人能举报：否则任何人都能拿消息 id 去试，试出哪些消息存在。
    """
    owner: int | None = None
    if target_type == "task":
        from app.modules.task.models import Task

        t = db.get(Task, target_id)
        owner = t.creator_id if t else None
        found = t is not None
    elif target_type == "content":
        from app.modules.content.models import Content

        c = db.get(Content, target_id)
        owner = c.author_id if c else None
        found = c is not None
    elif target_type == "user":
        u = db.get(User, target_id)
        found = u is not None and not u.is_deleted
        owner = target_id if found else None
    else:  # message
        from app.modules.im.models import ConversationMember, Message

        m = db.get(Message, target_id)
        found = m is not None and db.get(ConversationMember, (m.conversation_id, user.id)) is not None
        owner = m.sender_id if found and m else None
    if not found:
        raise not_found(f"要举报的{TARGET_LABELS[target_type]}找不到了（可能已经删除）；刷新页面再看看", "report_target_not_found")
    if owner == user.id:
        raise bad_request(f"这是你自己的{TARGET_LABELS[target_type]}，不能举报；要删除或修改请直接去编辑", "report_own_target")


def pending_duplicate(db: Session, user_id: int, target_type: str, target_id: int) -> Report | None:
    """同一个人对同一个对象已经有一条没处理的举报：不再新建（RISK-012）。"""
    return (db.query(Report)
            .filter(Report.reporter_id == user_id, Report.target_type == target_type,
                    Report.target_id == target_id, Report.status == "pending")
            .order_by(Report.id).first())


def check_daily_limit(db: Session, user_id: int) -> None:
    since = utcnow() - timedelta(days=1)
    n = db.query(Report).filter(Report.reporter_id == user_id, Report.created_at >= since).count()
    if n >= DAILY_LIMIT:
        raise too_many_requests(f"你这 24 小时里已经举报了 {n} 次，到了每天 {DAILY_LIMIT} 次的上限；"
                                "已经提交的都会处理，明天还可以继续举报，急事请联系客服", "report_daily_limit",
                                retry_after=3600)


def view(r: Report) -> dict:
    """举报人自己看到的一条：不带审核员是谁。"""
    return {
        "id": r.id,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "category": r.category or "other",
        "category_label": REPORT_CATEGORIES.get(r.category or "other", "其他"),
        "reason": r.reason,
        "status": r.status,
        "result": RESULT_LABELS.get(r.action, "") if r.status == "resolved" else "",
        "created_at": iso(r.created_at),
        "resolved_at": iso(r.resolved_at),
    }


def sla_view(r: Report, now=None) -> dict:
    """队列里一条的轻重与时限：等了几个小时、时限几个小时、超没超（时间差在服务端算好，客户端不自己解析时间）。"""
    now = now or utcnow()
    urgent = (r.category or "other") in URGENT_CATEGORIES
    sla = SLA_HOURS["urgent" if urgent else "normal"]
    waited = max(0, int((now - r.created_at).total_seconds() // 3600)) if r.created_at else 0
    return {"urgent": urgent, "waited_hours": waited, "sla_hours": sla,
            "overdue": r.status == "pending" and waited >= sla}


def mine(db: Session, user_id: int, limit: int = 50) -> list[dict]:
    rows = (db.query(Report).filter(Report.reporter_id == user_id)
            .order_by(Report.id.desc()).limit(limit).all())
    return [view(r) for r in rows]


def notify_reporter(db: Session, r: Report) -> None:
    """处理完告诉举报人结果（RISK-013）。系统自动生成的风控举报（reporter_id=0）没有人可告诉。"""
    if not r.reporter_id:
        return
    from app.modules.notification.service import notify

    what = TARGET_LABELS.get(r.target_type, "对象")
    notify(db, r.reporter_id, "system", "你的举报已处理",
           f"你举报的{what}（#{r.target_id}）：{RESULT_LABELS.get(r.action, '已处理')}。谢谢你帮忙维护社区。")


def export_mine(db: Session, user_id: int) -> dict:
    """数据导出（RISK-015）：有才带，没举报过的导出与以前一样。"""
    rows = mine(db, user_id, limit=10_000)
    return {"reports": rows} if rows else {}
