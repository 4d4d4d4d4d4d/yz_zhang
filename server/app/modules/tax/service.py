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
    acct.available_cents = 0
    wallet._log(db, TAX_USER_ID, "tax_remit", -amount, None, "代扣税款缴库")
    return {"remitted_cents": amount,
            "note": "已划出待缴税款；真实环境此处对应向税务专户的实际划款与申报"}


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
             "at": r.created_at.isoformat()}
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
             "rule": r.rule, "at": r.created_at.isoformat()}
            for r in rows
        ],
    }
