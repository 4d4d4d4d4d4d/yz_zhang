"""VER 核验单的资金、准入与结论处理（49 号 spec）。"""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import bad_request, conflict, forbidden
from app.modules.account.models import User, utcnow
from app.modules.wallet import service as wallet

from .models import UNBLOCKING_OUTCOMES, VerificationLesson, VerificationOrder

# 核验是「看一遍」不是「重做」：定价按原任务的一个比例，并设上下限。
# 做成按重做收费，等于让发布方为 AI 的不确定性付两次全价。
FEE_BPS = 1500          # 15%
FEE_MIN_CENTS = 500
FEE_MAX_CENTS = 20000


def fee_for(task) -> int:
    return max(FEE_MIN_CENTS, min(FEE_MAX_CENTS, task.budget_cents * FEE_BPS // 10000))


def verifier_block(db: Session, task, order: VerificationOrder, user: User) -> str:
    """VER-020/021 能不能接这一单核验；空串表示可以。

    单一判断来源：接单端点与「可接核验列表」读同一个函数。
    """
    # VER-020 **让 AI 核验 AI 的产出，是把同一个不确定性叠两遍，不是降低它。**
    # 整条升级链路的价值就建立在「最后有一个人负责」上。
    if user.is_agent:
        return "AI 助理不能担任核验人"
    if not user.is_verified:
        return "需先完成实名认证"
    if user.is_banned or user.is_deleted:
        return "账号不可用"
    # VER-021 利益冲突不靠自觉
    if user.id in (task.creator_id, task.executor_id):
        return "本单当事人不能核验本单"
    if order.payer_id == user.id:
        return "付费方不能核验本单"
    if user.credit_score < settings.VERIFIER_MIN_CREDIT:
        return f"信用分需达到 {settings.VERIFIER_MIN_CREDIT}"
    if not _has_completed_in_category(db, user.id, task.category):
        return f"需有「{task.category}」类目的完成记录"
    return ""


def _has_completed_in_category(db: Session, user_id: int, category: str) -> bool:
    from app.modules.task.models import Task

    return (
        db.query(Task)
        .filter(Task.executor_id == user_id, Task.category == category,
                Task.status == "completed")
        .first()
        is not None
    )


def create_order(db: Session, task, *, trigger: str, agent_run_id: int | None,
                 payer_id: int) -> VerificationOrder:
    """VER-010 下单即预扣。

    不走 escrow 三态：常见情形下付款方是平台自己，让平台对自己托管没有意义。
    但**必须预扣**——核验人做完了拿不到钱，这个角色就没人做。
    """
    existing = (
        db.query(VerificationOrder)
        .filter(VerificationOrder.task_id == task.id,
                VerificationOrder.status.in_(("open", "claimed")))
        .first()
    )
    if existing:
        raise conflict("该任务已有进行中的核验单", "verification_in_progress")

    fee = fee_for(task)
    acct = wallet.get_or_create(db, payer_id)
    # 余额检查**只对用户做**，平台账户允许为负。
    #
    # 这不是放水，是选一个更不坏的失败方式：平台账户的钱来自佣金收入，
    # 冷启动时它是 0。如果因为「平台没钱」而拒绝下核验单，
    # 结果是**用户卡在一个交付不了的任务上**——他没做错任何事，
    # 却要为平台的现金状况买单，这比账面为负糟糕得多。
    #
    # 而负余额本身是**有意义的经营信号**：它说明核验成本超过了佣金收入。
    # 这个数字该出现在财务看板上被人看见，不该被一个「余额不足」挡掉。
    # 对账不变量不受影响——它比的是「余额 == 自己那本账的总和」，负数一样成立。
    if payer_id != wallet.PLATFORM_USER_ID:
        if acct.available_cents < fee:
            raise bad_request("余额不足以支付核验费", "insufficient_balance")
        # 预扣：用户 → 平台代管，结单时再转给核验人。
        # 预扣存在的意义是**保护核验人**——做完了拿不到钱，这个角色就没人做。
        acct.available_cents -= fee
        platform = wallet.get_or_create(db, wallet.PLATFORM_USER_ID)
        platform.available_cents += fee
        wallet._log(db, payer_id, "verify_hold", -fee, None, "核验费预扣")
        wallet._log(db, wallet.PLATFORM_USER_ID, "verify_hold", fee, None, "核验费预扣")
    # 付款方就是平台时**不做预扣**：那是从一个账户划到它自己，
    # 余额不变而流水多两行，账实就对不上了（对账立刻会报 platform_fee_backing）。
    # 预扣本来就是防「付款方不付」，而平台既是付款方又是代管方，防不了自己。
    # 钱在结单时直接从平台账户出。

    order = VerificationOrder(
        task_id=task.id, agent_run_id=agent_run_id, payer_id=payer_id,
        trigger=trigger, fee_cents=fee,
        deadline=utcnow() + timedelta(hours=settings.VERIFY_DEADLINE_HOURS),
    )
    db.add(order)
    db.flush()
    return order


def _refund(db: Session, order: VerificationOrder, memo: str) -> None:
    """退回预扣。平台自付的单没有预扣，自然也没有退回（对称）。"""
    if order.payer_id == wallet.PLATFORM_USER_ID:
        return
    platform = wallet.get_or_create(db, wallet.PLATFORM_USER_ID)
    platform.available_cents -= order.fee_cents
    payee = wallet.get_or_create(db, order.payer_id)
    payee.available_cents += order.fee_cents
    wallet._log(db, wallet.PLATFORM_USER_ID, "verify_refund", -order.fee_cents, None, memo)
    wallet._log(db, order.payer_id, "verify_refund", order.fee_cents, None, memo)


def cancel_order(db: Session, order: VerificationOrder, memo: str = "核验单取消") -> None:
    if order.status not in ("open", "claimed"):
        raise conflict("核验单已结束", "verification_closed")
    _refund(db, order, memo)
    order.status = "cancelled"
    order.finished_at = utcnow()


def submit_outcome(db: Session, order: VerificationOrder, task, *, outcome: str,
                   comment: str, revised_output: str) -> dict:
    """VER-004/030 提交结论。`revised` 的修正稿**要重新过平台判据**。"""
    from app.modules.agent import criteria as crit

    if order.status != "claimed":
        raise conflict("核验单不在处理中", "not_claimed")
    if outcome not in ("approved", "revised", "rejected"):
        raise bad_request("非法核验结论", "invalid_outcome")

    if outcome == "revised":
        if not revised_output.strip():
            raise bad_request("结论为「已修正」时必须提交修正稿", "revision_required")
        # **人工核验是加上去的一道，不是用来豁免原有那道的。**
        # 不重跑判据就有个洞：判据拦住了 agent 的输出，核验人（可能只想早点结单）
        # 提交一份同样不过判据的修正稿，却因为「人工核验通过了」而放行。
        results, all_passed = crit.evaluate(task.acceptance_criteria or [], revised_output)
        order.criteria_results = results
        if not all_passed:
            failed = [r["text"] for r in results if r["kind"] == "auto" and not r["passed"]]
            raise bad_request(
                "修正稿仍未通过验收判据：" + "；".join(failed), "criteria_failed"
            )

    order.outcome = outcome
    order.comment = comment
    order.revised_output = revised_output
    order.status = "done"
    order.finished_at = utcnow()

    # VER-010 结单即付
    platform = wallet.get_or_create(db, wallet.PLATFORM_USER_ID)
    platform.available_cents -= order.fee_cents
    verifier = wallet.get_or_create(db, order.verifier_id)
    verifier.available_cents += order.fee_cents
    wallet._log(db, wallet.PLATFORM_USER_ID, "verify_payout", -order.fee_cents, None, "核验费支付")
    wallet._log(db, order.verifier_id, "verify_payout", order.fee_cents, None, "核验报酬")

    _record_lesson(db, order, task)

    # AGT-063 核验通过即代 agent 提交交付。
    # 在此之前，闸门解除了却**没有任何东西去推那一下**：核验人交了结论、
    # 核验费也付了，任务还停在 in_progress，两边都没有按钮可按。
    #
    # `revised` 时交付物是**修正稿**，不是 agent 的原始产出——修正稿之所以
    # 存在正是因为原始产出不合格，把原始产出交出去等于让发布方验收一份
    # 已被判定为不合格的东西，而他还刚为核验费买过单。
    delivered = False
    if outcome in UNBLOCKING_OUTCOMES:
        from app.modules.agent import service as agent_service

        delivered = agent_service.submit_agent_delivery(
            db, task, note=order.revised_output if outcome == "revised" else "",
        )
    return {
        "outcome": outcome,
        "unblocked": outcome in UNBLOCKING_OUTCOMES,
        "delivered": delivered,
    }


def _record_lesson(db: Session, order: VerificationOrder, task) -> None:
    """VER-040 回流经验。需求里的「持续帮助迭代」靠的就是这条。

    脱敏：不写 user_id、不写精确地址、不写金额。只留「这类任务、这些判据、
    人怎么判的、为什么」——这正是下次能用上的部分。
    """
    summary = ""
    if order.outcome == "revised" and order.revised_output:
        summary = order.revised_output[:500]
    db.add(VerificationLesson(
        category=task.category,
        outcome=order.outcome,
        task_title=task.title[:120],
        criteria=[c.get("text", "") for c in (task.acceptance_criteria or [])],
        reason=order.comment[:1000],
        revision_summary=summary,
    ))


def latest_order(db: Session, task_id: int) -> VerificationOrder | None:
    return (
        db.query(VerificationOrder)
        .filter(VerificationOrder.task_id == task_id)
        .order_by(VerificationOrder.id.desc())
        .first()
    )


def unblocking_outcome(db: Session, task_id: int) -> str:
    """VER-022 最新一张已结核验单的解锁性结论（`approved` / `revised`），否则空串。

    返回结论本身而不是布尔：AGT-067 要按结论分开判——判据没过的 run
    只有「已修正」能解锁，「通过」不能（那是覆盖判据，不是满足判据）。
    """
    order = latest_order(db, task_id)
    if order and order.status == "done" and order.outcome in UNBLOCKING_OUTCOMES:
        return order.outcome
    return ""


def verification_unblocks_delivery(db: Session, task_id: int) -> bool:
    """VER-022 有没有一份「通过 / 已修正」的核验。"""
    return bool(unblocking_outcome(db, task_id))


def expire_overdue(db: Session) -> dict:
    """VER-041 超时未接单：自动退款，发布方可以重新下单。

    只过期 `open` 的。已被接单（`claimed`）的不自动退——那笔活可能正在做，
    钱退了人还在干，是更糟的状态；那种情况走人工。
    """
    now = utcnow()
    rows = (
        db.query(VerificationOrder)
        .filter(VerificationOrder.status == "open", VerificationOrder.deadline < now)
        .all()
    )
    for order in rows:
        _refund(db, order, "核验单超时未接单退回")
        order.status = "expired"
        order.finished_at = now
    return {"expired": len(rows)}


# ------------------------------------------------------- VER-051 经验回流
# 上限是刻意的：提示词不能随数据增长无限膨胀，否则今天能跑的 agent
# 三个月后会因为超长而失败。**一个会随数据增长而变坏的机制是定时炸弹，
# 不是功能。**
LESSON_LIMIT = 5
LESSON_REASON_CHARS = 300
LESSON_REVISION_CHARS = 400
# 只取「没通过」的：`approved` 说的是「这次做对了」，对下一次没有指导价值，
# 而提示词长度是有成本的。
LESSON_OUTCOMES = ("revised", "rejected")


def lessons_for(db: Session, category: str, limit: int = LESSON_LIMIT) -> list[VerificationLesson]:
    """同类目最近的非通过核验结论。

    **不跨类目**：保洁的核验结论对写代码没有帮助，混进去只会稀释真正相关的内容。
    """
    if not category:
        return []
    return (
        db.query(VerificationLesson)
        .filter(VerificationLesson.category == category,
                VerificationLesson.outcome.in_(LESSON_OUTCOMES))
        .order_by(VerificationLesson.id.desc())
        .limit(limit)
        .all()
    )


def lessons_prompt(rows: list[VerificationLesson]) -> str:
    """把核验结论拼成一段提示词。空列表返回空串——**不产生一段空的「经验」抬头**，
    那会让模型以为自己漏看了什么。"""
    if not rows:
        return ""
    lines = ["", "【同类任务上，人工核验指出过的问题】",
             "（以下来自真实核验结论，按时间倒序；请在本次产出中避免重蹈覆辙）"]
    for i, row in enumerate(rows, 1):
        verdict = "被要求修正" if row.outcome == "revised" else "被判定不通过"
        lines.append(f"{i}. 「{row.task_title}」{verdict}：{row.reason[:LESSON_REASON_CHARS]}")
        if row.revision_summary:
            lines.append(f"   核验人给出的修正方向：{row.revision_summary[:LESSON_REVISION_CHARS]}")
    return "\n".join(lines)
