"""通知（NTF-004）：领域事件 → 站内信 + 推送（NTF-002）。

站内信是「记录」，推送是「触达」。这一路的教训是两者不能混为一谈：
被诉方的答辩期是 48 小时，逾期即缺席裁决（DSPR-020）——用户不主动打开 App，
一条只存在于站内的答辩提醒和没有提醒差别不大。
"""
from sqlalchemy.orm import Session

from app.core.events import subscribe

from .models import Notification


# NTF-060 **必达通知声明表**：(类别, 标题) → 为什么它不能被关掉。
#
# 判定标准只有一条：
#   **错过它，用户会失去一个他本可以行使的权利，或者失去一笔钱。**
#
# 不满足这条的**不该**进表——把所有通知都做成不可关，等于把开关变成摆设，
# 用户会连真正重要的这几条一起屏蔽掉。
#
# 立这张表是因为：全仓三十多处 notify()，此前只有 3 处 force=True，
# 「哪些该必达」只存在于写的人当时的脑子里。待验收提醒就是这么漏的——
# 三天后钱自动放给对方，而提醒他的那条通知**可以被一个开关关掉**。
MUST_REACH: dict[tuple[str, str], str] = {
    ("task", "待验收提醒"): "不处理就等于默认同意：到期自动验收并放款",
    ("task", "纠纷已受理"): "错过答辩期 = 平台可缺席作出处理决定",
    ("task", "答辩期即将届满"): "同上，这是最后一次提醒",
    ("contract", "合约签署超期作废"): "作废后要重新走一遍成交，错过没法补",
    ("task", "任务已逾期"): "逾期直接影响违约与补偿的判定",
    ("task", "交付被驳回"): "执行方不知道被驳回就没法在期限内整改",
}


def notify(db: Session, user_id: int, category: str, title: str, body: str = "",
           force: bool = False) -> None:
    """DSPC-013 `force=True` 表示这条通知**不可被偏好开关关掉**。

    此前只有 `funds` 类是必达的。但「有人对你发起纠纷，你有 48 小时答辩，
    逾期缺席裁决」同样是错过就无法挽回的——把它归到 `task` 类，
    等于允许用户用一个通知开关放弃自己的陈述权。
    """
    # NTF-003 偏好开关（funds 类为资金必达通知，不可关闭 —— 12.B）
    # NTF-060 声明表里的也一样：进了表就不用每个调用点都记得写 force=True，
    # **要不要必达是一条产品判断，不该散落在三十个调用点里**
    if category != "funds" and not force and (category, title) not in MUST_REACH:
        from app.modules.support.models import NotificationPref

        pref = (
            db.query(NotificationPref)
            .filter(NotificationPref.user_id == user_id, NotificationPref.category == category)
            .first()
        )
        if pref and not pref.enabled:
            return
    db.add(Notification(user_id=user_id, category=category, title=title, body=body))
    # NTF-002 推送走**发件箱**，不在这里直接打供应商：
    # ① 通知常在业务事务里发出，同步打第三方会把一次网络抖动变成一笔交易失败；
    # ② 发件箱本来就有重试、死信与跨副本补做（EVT-021），推送白拿这些能力。
    from app.core.events import publish

    publish(db, "notification.created", {
        "user_id": user_id, "category": category, "title": title, "body": body,
    })


def _task(db: Session, task_id: int):
    from app.modules.task.models import Task

    return db.get(Task, task_id)


def _on_task_matched(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "task", "报名被采纳",
               f"你已被选为任务《{task.title}》的执行者，请尽快签署合约")


def _on_contract_funded(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "funds", "资金已托管",
               f"任务《{task.title}》资金已托管，可以开始执行")


def _on_contract_released(db, payload):
    task = _task(db, payload["task_id"])
    if task and task.executor_id:
        notify(db, task.executor_id, "funds", "任务款已到账",
               f"任务《{task.title}》验收通过，款项已入钱包")


def _on_task_pending_acceptance(db, payload):
    """NTF-061/AGT-070 说清三件事：谁交的、几天后自动放款、还能做什么。

    改造前这句是「已提交验收，超时将自动通过」——**没说几天**，
    而 `AUTO_ACCEPT_DAYS` 默认是 3。用户无从知道该什么时候回来看。
    与 V61 修过的纠纷通知同一条：**通知里的数字不许是字面量，也不许没有**。
    """
    from app.core.config import settings
    from app.modules.account.models import User

    task = _task(db, payload["task_id"])
    if not task:
        return
    days = settings.AUTO_ACCEPT_DAYS
    executor = db.get(User, task.executor_id) if task.executor_id else None
    if executor and executor.is_agent:
        # AGT-070 发布方可能根本没意识到这一单是 AI 做的（尽管是他自己邀请的），
        # 而 N 天后就自动放款了。人工核验那条路 V74 就建好了，
        # 他只是在这个时点不知道它存在。
        body = (
            f"任务《{task.title}》由平台 AI 助理完成并提交交付，平台为本任务履约的"
            f"责任主体。请在 {days} 天内验收或驳回；逾期未处理将自动验收并放款。"
            f"如需人工把关，可在任务详情页申请人工核验。"
        )
    else:
        body = (
            f"任务《{task.title}》已提交验收。请在 {days} 天内验收或驳回；"
            f"逾期未处理将自动验收并放款。"
        )
    notify(db, task.creator_id, "task", "待验收提醒", body)


def _on_dispute_opened(db, payload):
    """DSPC-012 通知必须带上纠纷 id，小时数必须取自配置。

    改造前这句是：「相关资金已冻结，请在 48 小时内协商或提交证据」——
    三处都不成立：没有任何客户端能「提交证据」；通知里没有 `dispute_id`，
    而被诉方拿不到它（发起方才有 `POST /disputes` 的返回值）；
    `48` 是硬编码字面量，运维改了 `PLATFORM_DISPUTE_RESPONSE_HOURS`
    这句话会继续理直气壮地说 48。
    """
    from app.core.config import settings

    hours = settings.DISPUTE_RESPONSE_HOURS
    for uid in payload.get("parties", []):
        notify(db, uid, "task", "纠纷已受理",
               f"任务 #{payload.get('task_id')} 的相关资金已冻结。"
               f"请在 {hours} 小时内在任务详情页提交答辩与证据，或与对方协商和解；"
               "逾期未答辩，平台可缺席作出处理决定。",
               force=True)


def push_to_devices(db: Session, payload: dict) -> dict:
    """NTF-002 把一条通知推到用户的设备上。

    由发件箱驱动（`notification.created`），所以：失败会重试，重试耗尽进死信，
    而且**绝不会把一笔放款回滚掉**。
    """
    from app.vendors import base as vendor_base
    from app.vendors.registry import get_provider

    from .models_device import DeviceToken

    provider = get_provider("push")
    if not getattr(provider, "delivers", False):
        return {"delivered": 0, "reason": "no_push_provider"}

    user_id = payload.get("user_id")
    rows = (
        db.query(DeviceToken)
        .filter(DeviceToken.user_id == user_id, DeviceToken.revoked.is_(False))
        .all()
    )
    if not rows:
        return {"delivered": 0, "reason": "no_device"}

    tokens = [r.token for r in rows]
    result = vendor_base.call(
        db, "push", provider.name, "send", {"count": len(tokens)},
        lambda: provider.send(tokens, payload.get("title", ""), payload.get("body", ""),
                              {"category": payload.get("category", "")}),
    )
    # 供应商回报的失效令牌必须落地清理：设备卸载后令牌永久失效，
    # 不清理就会年复一年地推给不存在的设备，而通道按量计费
    invalid = set(result.data.get("invalid_tokens") or [])
    for row in rows:
        if row.token in invalid:
            row.revoked = True
            db.add(row)
    return {"delivered": result.data.get("delivered", 0), "revoked": len(invalid)}


def _on_notification_created(db, payload):
    push_to_devices(db, payload)


def register_event_handlers() -> None:
    # 通知补发晚一点也还是有用的信息，且失败时写入已被保存点回滚，重试从干净状态重来
    subscribe("task.matched", _on_task_matched, retry=True)
    subscribe("contract.funded", _on_contract_funded, retry=True)
    subscribe("contract.released", _on_contract_released, retry=True)
    subscribe("task.pending_acceptance", _on_task_pending_acceptance, retry=True)
    subscribe("dispute.opened", _on_dispute_opened, retry=True)
    # NTF-002 推送：retry=True——第三方网关抖动是常态，重试是必须的；
    # 而它绝不能拖垮业务事务，所以走发件箱而不是同步调用
    subscribe("notification.created", _on_notification_created, retry=True)
