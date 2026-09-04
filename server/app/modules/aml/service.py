"""AML-001~032 可疑识别、阈值判定与留痕（30 号 spec）。

设计边界（写在最前面，因为很容易越界）：

- 代码只识别**平台看得见而存管方看不见**的东西：业务语义。
  存管机构只看到资金流，不知道哪笔钱对应哪个任务、双方是不是同一个人的马甲。
- 代码**绝不自动对外报送**。报送是合规官的动作，要人判断、要签字。
  这里只做识别、留痕、转人审、可导出。
- 代码**绝不把可疑标记透给用户**（AML-030 tipping-off）：
  所有面向用户的文案都必须中性。
"""
from datetime import timedelta

from sqlalchemy import func

from app.core.config import settings
from app.modules.account.models import utcnow

from .models import PATTERNS, SuspiciousActivity

# AML-031 用户可见的中性措辞。**唯一**允许给用户看的说法。
NEUTRAL_REVIEW_MESSAGE = "该笔提现需人工复核，通常 1 个工作日内处理完成"


def flag(db, user_id: int, pattern: str, detail: str, amount_cents: int = 0,
         ref_type: str = "", ref_id: int = 0) -> SuspiciousActivity | None:
    """记一条可疑活动。同一主体+形态+关联对象不重复记。"""
    if pattern not in PATTERNS:
        raise ValueError(f"未知的可疑形态 {pattern}")
    existing = (
        db.query(SuspiciousActivity)
        .filter(SuspiciousActivity.user_id == user_id,
                SuspiciousActivity.pattern == pattern,
                SuspiciousActivity.ref_type == ref_type,
                SuspiciousActivity.ref_id == ref_id,
                SuspiciousActivity.status == "pending")
        .first()
    )
    if existing:
        return existing
    row = SuspiciousActivity(user_id=user_id, pattern=pattern, detail=detail,
                             amount_cents=amount_cents, ref_type=ref_type, ref_id=ref_id)
    db.add(row)
    db.flush()
    return row


# ---------- AML-001/010 提现阈值与拆分 ----------
def _recent_withdrawals(db, user_id: int, hours: int) -> list:
    from app.modules.wallet.models import LedgerEntry

    cutoff = utcnow() - timedelta(hours=hours)
    return (
        db.query(LedgerEntry)
        .filter(LedgerEntry.user_id == user_id,
                LedgerEntry.kind.in_(("withdraw", "withdraw_hold")),
                LedgerEntry.created_at >= cutoff)
        .all()
    )


def assess_withdrawal(db, user_id: int, amount_cents: int, today_withdrawn: int) -> dict:
    """提现前的风控判定。返回是否转人审，以及要记的可疑形态。

    **必须在钱包锁内调用**：并发提现各自读到「还没超」再分别放行，
    和拆分是同一个洞的两种利用姿势（AML-003）。

    `today_withdrawn` 由调用方在锁内算好传进来——不在这里重算，
    是为了保证它和调用方做余额判断时用的是同一个数。
    """
    reasons: list[tuple[str, str, int]] = []   # (pattern, detail, amount)
    cumulative = today_withdrawn + amount_cents

    single_hit = amount_cents >= settings.LARGE_WITHDRAW_CENTS
    # AML-001 这一条是本批次的核心：只判单笔的话，减 1 元多点几次就能绕过
    cumulative_hit = cumulative >= settings.AML_DAILY_REVIEW_CENTS

    # **不变量：被扣下的提现必须带着理由。**
    # 只把钱冻住却不写为什么，复核的人打开队列看到一堆没有说明的条目，
    # 只能全部放行——那等于风控没做，还平白让用户等了一天。
    if single_hit:
        reasons.append((
            "large_amount",
            f"单笔提现 {amount_cents / 100:.2f} 元，达到单笔人审门槛 "
            f"{settings.LARGE_WITHDRAW_CENTS / 100:.2f} 元",
            amount_cents,
        ))
    elif cumulative_hit:
        reasons.append((
            "large_amount",
            f"当日累计提现 {cumulative / 100:.2f} 元（本次 {amount_cents / 100:.2f} 元），"
            f"达到累计人审门槛 {settings.AML_DAILY_REVIEW_CENTS / 100:.2f} 元",
            cumulative,
        ))
    if cumulative >= settings.AML_REPORT_CENTS:
        reasons.append((
            "large_amount",
            f"当日累计提现 {cumulative / 100:.2f} 元，达到大额报告线 "
            f"{settings.AML_REPORT_CENTS / 100:.2f} 元",
            cumulative,
        ))

    if cumulative_hit and not single_hit:
        # 单笔没到线、累计到了 → 正是拆分的特征
        near = settings.LARGE_WITHDRAW_CENTS * settings.AML_NEAR_THRESHOLD_PCT // 100
        recent = _recent_withdrawals(db, user_id, settings.AML_STRUCTURING_HOURS)
        near_count = sum(1 for e in recent if near <= abs(e.amount_cents) < settings.LARGE_WITHDRAW_CENTS)
        if amount_cents >= near:
            near_count += 1
        if near_count >= settings.AML_STRUCTURING_COUNT:
            reasons.append((
                "structuring",
                f"{settings.AML_STRUCTURING_HOURS} 小时内 {near_count} 笔提现金额在 "
                f"{near / 100:.0f}~{settings.LARGE_WITHDRAW_CENTS / 100:.0f} 元之间"
                f"（均低于单笔人审门槛），当日累计 {cumulative / 100:.2f} 元",
                cumulative,
            ))

    passthrough = _detect_passthrough(db, user_id, amount_cents)
    if passthrough:
        reasons.append(passthrough)

    # needs_review 与 reasons 现在是等价的：有理由才扣，扣了就有理由
    return {"needs_review": bool(reasons), "reasons": reasons,
            "cumulative_cents": cumulative}


def _detect_passthrough(db, user_id: int, amount_cents: int):
    """AML-011 快进快出：充值后短时间内几乎原样提现，中间没有真实成交。

    「中间没有真实成交」是关键——有成交说明钱是挣来的，那是正常业务；
    没有成交而钱进了又出，平台就只是被当成了通道。
    """
    from app.modules.wallet.models import LedgerEntry

    cutoff = utcnow() - timedelta(hours=settings.AML_PASSTHROUGH_HOURS)
    topped = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == user_id, LedgerEntry.kind == "topup",
                LedgerEntry.created_at >= cutoff)
        .scalar()
    ) or 0
    if topped <= 0:
        return None
    earned = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == user_id,
                LedgerEntry.kind.in_(("escrow_release", "dispute_split")),
                LedgerEntry.created_at >= cutoff)
        .scalar()
    ) or 0
    if earned > 0:
        return None      # 钱是挣来的，正常业务
    if amount_cents * 100 < int(topped) * settings.AML_PASSTHROUGH_PCT:
        return None
    return (
        "passthrough",
        f"{settings.AML_PASSTHROUGH_HOURS} 小时内充值 {int(topped) / 100:.2f} 元、"
        f"无任何任务收入，本次提现 {amount_cents / 100:.2f} 元"
        f"（占充值额 {amount_cents * 100 // max(int(topped), 1)}%）",
        amount_cents,
    )


def record_withdrawal_flags(db, user_id: int, reasons: list, request_id: int) -> None:
    for pattern, detail, amount in reasons:
        flag(db, user_id, pattern, detail, amount, "withdraw_request", request_id)


# ---------- AML-013 收款账户聚集 ----------
def check_payout_clustering(db, user_id: int, account_no: str) -> None:
    """多个不同用户绑定同一收款账户。

    一人多号已由证件号摘要查重拦住，但**收款账户**这一维度此前没人看：
    十个实名账号把钱打到同一张卡，是最朴素的资金归集。

    这里刻意**只标记不拦截**：夫妻共用一张卡、帮父母代收，都是真实场景。
    风控做成硬拦截会误伤这些人；交给人复核才分得清。
    """
    from app.modules.wallet.models import PayoutAccount

    if not account_no:
        return
    others = (
        db.query(PayoutAccount)
        .filter(PayoutAccount.account_no == account_no,
                PayoutAccount.user_id != user_id)
        .all()
    )
    if not others:
        return
    ids = sorted({o.user_id for o in others} | {user_id})
    flag(db, user_id, "account_clustering",
         f"该收款账户已被 {len(ids)} 个账号绑定：用户 {ids}",
         0, "payout_account", user_id)


# ---------- 管理端 ----------
def listing(db, status: str = "pending", limit: int = 100) -> dict:
    q = db.query(SuspiciousActivity)
    if status != "all":
        q = q.filter(SuspiciousActivity.status == status)
    rows = q.order_by(SuspiciousActivity.id.desc()).limit(limit).all()
    return {
        "items": [
            {"id": r.id, "user_id": r.user_id, "pattern": r.pattern,
             "pattern_label": PATTERNS.get(r.pattern, r.pattern),
             "detail": r.detail, "amount_cents": r.amount_cents,
             "ref_type": r.ref_type, "ref_id": r.ref_id, "status": r.status,
             "review_note": r.review_note, "at": r.created_at.isoformat()}
            for r in rows
        ],
        "note": (
            "本清单及其内容属反洗钱工作信息，依《反洗钱法》第五条应予保密，"
            "不得向客户或其他无关人员泄露。平台不自动对外报送，"
            "报送与否由合规官判断。"
        ),
    }


def review(db, activity_id: int, admin_id: int, decision: str, note: str = "") -> dict:
    from app.core.errors import bad_request, not_found

    if decision not in ("cleared", "to_report", "reported"):
        raise bad_request("非法的复核结论", "invalid_decision")
    row = db.get(SuspiciousActivity, activity_id)
    if not row:
        raise not_found("记录不存在")
    row.status = decision
    row.reviewer_id = admin_id
    row.review_note = note
    row.reviewed_at = utcnow()
    db.add(row)
    return {"id": row.id, "status": row.status}


def stats(db) -> dict:
    rows = db.query(SuspiciousActivity).all()
    by_status: dict[str, int] = {}
    by_pattern: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_pattern[r.pattern] = by_pattern.get(r.pattern, 0) + 1
    return {"total": len(rows), "by_status": by_status, "by_pattern": by_pattern}
