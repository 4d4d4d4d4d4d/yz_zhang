"""MOD-001 处置动作的**单一实现**（33 号 spec）。

此前封禁有两条路：`/admin/users/{id}/ban` 做全套（算影响面、通知在途合约
对手方、关闭报名、下架挂单、记审计），而审核队列的
`/admin/reports/{id}/resolve` 只有两行——

    user.is_banned = True
    db.add(user)

上面五件事一件都没做。而**审核队列恰恰是审核员日常真正在用的那个界面**。

后果不是「少了点提示」：在途合约的对手方永远不会被告知他的钱还托管在
一个已被封禁、永远不会来验收的人那里——OPS-013 整节就是为了防止这件事。

同一个业务动作只能有一个实现。端点负责鉴权取参，副作用全在这里。
"""
from sqlalchemy.orm import Session

from app.modules.account.models import User
from app.modules.contract.models import Contract
from app.modules.task.models import Application, Task


def ban_impact(db: Session, user_id: int) -> dict:
    """OPS-013 封禁影响面：在途合约 / 托管资金 / 钱包余额 / 未成交挂单。

    封禁会让该用户无法交付或验收，其对手方的托管资金将被无限期困住——
    封禁前必须让管理员看见这个爆炸半径。
    """
    from app.modules.wallet.service import get_or_create

    in_flight = (
        db.query(Contract)
        .filter(
            (Contract.requester_id == user_id) | (Contract.executor_id == user_id),
            Contract.status.in_(("pending_signatures", "signed", "funded")),
        )
        .all()
    )
    acct = get_or_create(db, user_id)
    # 未成交的挂单：封禁后无人能选人，须下架，否则工人白报名空等
    open_tasks = (
        db.query(Task)
        .filter(Task.creator_id == user_id, Task.status.in_(("draft", "published")))
        .all()
    )
    return {
        "in_flight_contracts": [
            {"contract_id": c.id, "task_id": c.task_id, "status": c.status,
             "amount_cents": c.amount_cents,
             "counterparty_id": c.executor_id if c.requester_id == user_id else c.requester_id}
            for c in in_flight
        ],
        "in_flight_count": len(in_flight),
        "escrow_at_risk_cents": sum(
            c.amount_cents - c.released_cents for c in in_flight if c.status == "funded"
        ),
        "open_task_ids": [t.id for t in open_tasks],
        "open_task_count": len(open_tasks),
        "wallet": {"available_cents": acct.available_cents,
                   "escrow_cents": acct.escrow_cents, "frozen_cents": acct.frozen_cents},
    }


def ban_user(db: Session, admin_id: int, user_id: int, reason: str = "") -> dict:
    """MOD-002 封禁的**唯一**实现：五步一步都不能少。

    「从哪个入口进来的」不该改变用户拿不拿得到通知。
    """
    from app.core.errors import bad_request, not_found
    from app.modules.notification.service import notify
    from app.modules.task.service import transition

    from .router import record_audit

    user = db.get(User, user_id)
    if not user:
        raise not_found("用户不存在")
    if user.is_admin:
        raise bad_request("不能封禁管理员", "cannot_ban_admin")

    impact = ban_impact(db, user_id)
    user.is_banned = True
    db.add(user)

    # 1) 通知在途合约的对手方：被封用户无法再交付/验收，
    #    请及时取消或发起纠纷，避免托管资金无限期困住
    for c in impact["in_flight_contracts"]:
        notify(db, c["counterparty_id"], "task", "对方账号已被封禁",
               f"任务 #{c['task_id']}（合约 #{c['contract_id']}）的对方账号已被平台封禁，"
               "无法继续履约。请尽快取消任务或发起纠纷，以便结清托管资金。")

    # 2) 下架未成交挂单：封禁后无人能选人，留在广场只会让工人白报名空等
    for task_id in impact["open_task_ids"]:
        task = db.get(Task, task_id)
        if not task:
            continue
        pending = db.query(Application).filter(
            Application.task_id == task_id, Application.status == "pending"
        ).all()
        for a in pending:
            a.status = "rejected"
            db.add(a)
            notify(db, a.applicant_id, "task", "报名的任务已下架",
                   f"《{task.title}》的发布方账号已被封禁，任务已下架，你的报名已自动关闭。")
        transition(db, task, "cancelled", {"cancelled_by": "system_creator_banned"})

    record_audit(db, admin_id, "ban_user", "user", user_id,
                 f"{reason + '；' if reason else ''}"
                 f"在途合约 {impact['in_flight_count']} 笔，"
                 f"涉险托管 {impact['escrow_at_risk_cents']} 分，"
                 f"下架挂单 {impact['open_task_count']} 个")
    return {"id": user.id, "is_banned": True, "impact": impact}


def takedown_task(db: Session, admin_id: int, task_id: int, reason: str) -> dict:
    """MOD-003 下架任务：**走状态机**，并告诉受影响的人。

    此前是 `task.status = "cancelled"` 直接赋值：绕过白名单校验、不派发
    `task.cancelled` 事件（下一个给这个事件加订阅者的人——比如托管退款——
    会发现它在这条路径上根本不触发），而且发布者和报名者都收不到任何通知——
    任务就这么消失了，不知道为什么，也就无从申诉。
    """
    from app.modules.notification.service import notify
    from app.modules.task.service import transition

    from .router import record_audit

    task = db.get(Task, task_id)
    if not task:
        return {"task_id": task_id, "removed": False, "note": "任务不存在"}
    if task.status not in ("draft", "published"):
        # 已成交的任务牵涉托管资金，不能被审核动作单方作废——走纠纷流程
        return {"task_id": task_id, "removed": False,
                "note": "任务已成交，涉及托管资金，请走纠纷流程处理"}

    pending = db.query(Application).filter(
        Application.task_id == task_id, Application.status == "pending"
    ).all()
    for a in pending:
        a.status = "rejected"
        db.add(a)
        notify(db, a.applicant_id, "task", "报名的任务已下架",
               f"《{task.title}》因违规被下架，你的报名已自动关闭。")
    notify(db, task.creator_id, "task", "任务已被下架",
           f"《{task.title}》因{reason or '违反平台规则'}被下架。"
           "如有异议可通过客服申诉。")
    transition(db, task, "cancelled", {"cancelled_by": "moderation"})
    record_audit(db, admin_id, "takedown_task", "task", task_id, reason)
    return {"task_id": task_id, "removed": True,
            "notified_applicants": len(pending)}


def takedown_content(db: Session, admin_id: int, content_id: int, reason: str) -> dict:
    """MOD-003 下架内容并通知作者。"""
    from app.modules.content.models import Content
    from app.modules.notification.service import notify

    from .router import record_audit

    content = db.get(Content, content_id)
    if not content:
        return {"content_id": content_id, "removed": False, "note": "内容不存在"}
    content.status = "removed"
    db.add(content)
    notify(db, content.author_id, "content", "内容已被下架",
           f"你的内容因{reason or '违反平台规则'}已被下架。如有异议可通过客服申诉。")
    record_audit(db, admin_id, "takedown_content", "content", content_id, reason)
    return {"content_id": content_id, "removed": True}
