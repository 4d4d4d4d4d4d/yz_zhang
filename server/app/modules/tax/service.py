"""TAX-010~014 代扣的钱怎么走、怎么对账、怎么缴库。

关键设计：**代扣的钱进独立专户**（`TAX_USER_ID`）。它既不是平台收入，
也不再是执行者的钱，而是平台代持、待缴库的第三方资金。
混进平台佣金账户是最容易犯也最难查的错——账面上平台「赚」多了，
等到缴库时才发现那笔钱早被当成收入结算走了。
"""
from sqlalchemy import func

from app.core.config import settings
from app.modules.wallet import service as wallet
from app.vendors.tax import TaxAssessment

from .models import TaxWithholding
from app.core.timefmt import iso

# 代扣税款专户。平台佣金是 0，这里用 -1：负数一眼就能看出「不是普通用户」
TAX_USER_ID = -1


def enabled() -> bool:
    """只有显式声明代扣才扣。self_declared / none 都不扣，但含义完全不同。"""
    return settings.TAX_MODE == "withholding"


def assess(income_cents: int, context: dict | None = None) -> TaxAssessment:
    from app.vendors.registry import get_provider

    if not enabled():
        from app.vendors.tax import NoWithholdingTax

        return NoWithholdingTax().assess(income_cents, context or {})
    return get_provider("tax").assess(income_cents, context or {})


def withhold(db, user_id: int, contract_id: int, income_cents: int,
             kind: str = "release") -> TaxWithholding | None:
    """把税款从执行者应得里划到税款专户，并留下完税明细。

    返回 None 表示本次不扣（模式为 none/self_declared，或税额为 0）。
    调用方据此决定分账里有没有第三个收款方。
    """
    result = assess(income_cents, {"user_id": user_id, "contract_id": contract_id})
    if result.withheld_cents <= 0:
        return None
    # 先全额确认收入、再从中代扣——两条流水如实反映「他挣了多少、被扣了多少」，
    # 直接按净额入账会让执行者在流水里看不到自己被扣过税
    payee = wallet.get_or_create(db, user_id)
    if payee.available_cents < result.withheld_cents:
        from app.core.errors import bad_request

        raise bad_request("代扣税款超过可用余额", "tax_exceeds_balance")
    payee.available_cents -= result.withheld_cents
    wallet._log(db, user_id, "tax_withheld", -result.withheld_cents, contract_id,
                "代扣个人所得税")
    acct = wallet.get_or_create(db, TAX_USER_ID)
    acct.available_cents += result.withheld_cents
    wallet._log(db, TAX_USER_ID, "tax_withheld", result.withheld_cents, contract_id,
                "代扣个人所得税（专户）")
    row = TaxWithholding(
        user_id=user_id, contract_id=contract_id, settlement_kind=kind,
        income_cents=income_cents, taxable_cents=result.taxable_cents,
        withheld_cents=result.withheld_cents, rule=result.rule,
        mode=settings.TAX_MODE, note=result.note,
    )
    db.add(row)
    db.flush()
    return row


def remit(db) -> dict:
    """TAX-013 缴库：把专户余额划出系统。

    形态与平台收入对公结算（`platform_settle`）一致——接真实税务通道后
    换的是执行者，不是形态。
    """
    acct = wallet.get_or_create(db, TAX_USER_ID)
    amount = acct.available_cents
    if amount <= 0:
        return {"remitted_cents": 0, "note": "专户无待缴余额"}
    # PAY-042d（287 号 spec）大额先出草稿、人确认：钱与申报，AI 和 job 都只出草稿
    if amount >= settings.TAX_REMIT_CONFIRM_CENTS:
        from .models import TaxRemitRequest

        pending = db.query(TaxRemitRequest).filter(TaxRemitRequest.status == "awaiting_confirm").first()
        if pending is None:
            pending = TaxRemitRequest(amount_cents=amount)
            db.add(pending)
            db.flush()
            _notify_finance(db, "有一笔代扣税款等你确认缴库",
                            f"缴库草稿 #{pending.id}：¥{amount / 100:.2f}。请与本期申报数核对后，"
                            "在管理后台「平台收支 → 待确认的缴库」确认划出；对不上就驳回并写明原因。")
        return {"remitted_cents": 0, "pending_request_id": pending.id, "pending_cents": pending.amount_cents,
                "note": f"待缴税款达到 ¥{settings.TAX_REMIT_CONFIRM_CENTS / 100:.2f}，已生成缴库草稿，"
                        "等财务核对申报数后确认才会划出"}
    remit_amount(db, acct, amount)
    return {"remitted_cents": amount,
            "note": "已划出待缴税款；真实环境此处对应向税务专户的实际划款与申报"}


# PAY-042f（291 号 spec）缴库草稿等确认超过这么多天，每天催一次财务
TAX_REMIT_REMIND_DAYS = 3


def remind_remits(db) -> dict:
    """等确认超过 3 天的缴库草稿：催财务，一天最多一次；处理了就不催。"""
    from datetime import timedelta

    from app.modules.account.models import utcnow

    from .models import TaxRemitRequest

    now = utcnow()
    due = (db.query(TaxRemitRequest)
           .filter(TaxRemitRequest.status == "awaiting_confirm",
                   TaxRemitRequest.created_at <= now - timedelta(days=TAX_REMIT_REMIND_DAYS))
           .order_by(TaxRemitRequest.id).all())
    due = [r for r in due if r.reminded_at is None or r.reminded_at <= now - timedelta(hours=24)]
    if not due:
        return {"reminded": 0}
    for r in due:
        days = (now - r.created_at).days
        _notify_finance(db, "缴库草稿还没确认",
                        f"缴库草稿 #{r.id}（¥{r.amount_cents / 100:.2f}）已经等了 {days} 天。代扣的税款要按期申报缴纳，"
                        "请在管理后台「平台收支 → 待确认的缴库」与申报数核对后确认；对不上就驳回并写明原因。")
        r.reminded_at = now
        db.add(r)
    return {"reminded": len(due)}


def remit_amount(db, acct, amount: int) -> None:
    acct.available_cents -= amount
    wallet._log(db, TAX_USER_ID, "tax_remit", -amount, None, "代扣税款缴库")


def _notify_finance(db, title: str, body: str) -> int:
    from app.core.admin_roles import has_role
    from app.modules.account.models import User
    from app.modules.notification.service import notify

    ids = [u.id for u in db.query(User).filter(User.is_admin.is_(True), User.is_banned.is_(False)).order_by(User.id)
           if has_role(u, "finance")]
    for uid in ids:
        notify(db, uid, "system", title, body)
    return len(ids)


def account_balance(db) -> int:
    acct = db.get(wallet.WalletAccount, TAX_USER_ID)
    return acct.available_cents if acct else 0


def expected_balance(db) -> int:
    """TAX-012 第五条不变量的期望值：Σ代扣 − Σ已缴库。"""
    from app.modules.wallet.models import LedgerEntry

    total = (
        db.query(func.coalesce(func.sum(LedgerEntry.amount_cents), 0))
        .filter(LedgerEntry.user_id == TAX_USER_ID,
                LedgerEntry.kind.in_(("tax_withheld", "tax_remit")))
        .scalar()
    )
    return int(total)


def my_summary(db, user_id: int) -> dict:
    """TAX-021 执行者看到的代扣明细。

    措辞是刻意的：这是**代扣明细**，不是税务机关的完税证明。
    劳务报酬走的是预扣预缴，年度汇算时还要并入综合所得多退少补，
    让用户以为这份东西可以直接拿去抵扣，是在帮他犯错。
    """
    rows = (
        db.query(TaxWithholding)
        .filter(TaxWithholding.user_id == user_id)
        .order_by(TaxWithholding.id.desc())
        .all()
    )
    by_year: dict[int, dict] = {}
    for row in rows:
        slot = by_year.setdefault(row.created_at.year,
                                  {"income_cents": 0, "withheld_cents": 0, "count": 0})
        slot["income_cents"] += row.income_cents
        slot["withheld_cents"] += row.withheld_cents
        slot["count"] += 1
    return {
        "mode": settings.TAX_MODE,
        "yearly": [{"year": y, **v} for y, v in sorted(by_year.items(), reverse=True)],
        "items": [
            {"id": r.id, "contract_id": r.contract_id, "kind": r.settlement_kind,
             "income_cents": r.income_cents, "taxable_cents": r.taxable_cents,
             "withheld_cents": r.withheld_cents, "rule": r.rule, "note": r.note,
             "at": iso(r.created_at)}
            for r in rows
        ],
        "disclaimer": (
            "这是平台作为扣缴义务人出具的**代扣明细**，不是税务机关的完税证明。"
            "劳务报酬为预扣预缴，年度汇算清缴时并入综合所得多退少补；"
            "如需完税证明请通过自然人电子税务局查询下载。"
        ),
    }


def ledger(db, limit: int = 200) -> dict:
    """TAX-024 管理端台账。"""
    rows = (
        db.query(TaxWithholding).order_by(TaxWithholding.id.desc()).limit(limit).all()
    )
    withheld = (
        db.query(func.coalesce(func.sum(TaxWithholding.withheld_cents), 0)).scalar() or 0
    )
    return {
        "mode": settings.TAX_MODE,
        "provider": settings.TAX_PROVIDER,
        "total_withheld_cents": int(withheld),
        "account_balance_cents": account_balance(db),
        "pending_remit_cents": account_balance(db),
        "items": [
            {"id": r.id, "user_id": r.user_id, "contract_id": r.contract_id,
             "income_cents": r.income_cents, "withheld_cents": r.withheld_cents,
             "rule": r.rule, "at": iso(r.created_at)}
            for r in rows
        ],
    }
