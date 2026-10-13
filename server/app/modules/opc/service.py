"""一人公司工具的计算部分（124 号 spec）：期间、汇总与免税标准提示、申报日历、平台收入导入、合同体检。

**只出底稿与提醒**。汇总不是申报表，日历不是税务机关的通知，合同体检不是法律意见——每个出口都写明了。
口径来源写在 `POLICY` 里，带文号与有效期；过了有效期，提示自己会说「政策可能已变」。
"""
from __future__ import annotations

import calendar as _cal
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.core.timefmt import day

from .models import OpcEntry, OpcProfile

DISCLAIMER = "这是记账底稿与提醒，不是申报表，也不构成税务意见；申报以电子税务局的口径为准，拿不准请找专业的人。"
CONTRACT_DISCLAIMER = "这是按条款清单做的体检，不构成法律意见；金额大、条款复杂的合同请找执业律师审阅。"
# 口径与出处（124 号 spec 第 1 节逐条核过原文）
POLICY = {
    "vat_small": {"source": "财政部 税务总局公告2023年第19号", "valid_until": date(2027, 12, 31),
                  "text": "小规模纳税人月销售额 10 万元以下（含本数）免征增值税；适用 3% 征收率的减按 1%。按季申报的，季度销售额 30 万元以下免征"},
    "small_low_profit": {"source": "财政部 税务总局公告2023年第12号", "valid_until": date(2027, 12, 31),
                         "text": "小型微利企业减按 25% 计算应纳税所得额，按 20% 税率缴纳企业所得税"},
    "sole_prop_iit": {"source": "财政部 税务总局公告2023年第12号", "valid_until": date(2027, 12, 31),
                      "text": "个体工商户年应纳税所得额不超过 200 万元的部分，减半征收个人所得税"},
}
VAT_EXEMPT_CENTS = {"month": 100_000_00, "quarter": 300_000_00}
PLATFORM_INCOME_KINDS = ("escrow_release", "dispute_split", "agent_payout_in", "coop_distribution_in")


# ------------------------------------------------------------------ 期间
def parse_period(s: str) -> tuple[date, date, str]:
    """`2026-10`（月）、`2026-Q3`（季）、`2026`（年）→ [起, 止]（含）与种类。"""
    if m := re.fullmatch(r"(\d{4})-(\d{2})", s):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return date(y, mo, 1), date(y, mo, _cal.monthrange(y, mo)[1]), "month"
    if m := re.fullmatch(r"(\d{4})-Q([1-4])", s):
        y, q = int(m.group(1)), int(m.group(2))
        end_m = q * 3
        return date(y, end_m - 2, 1), date(y, end_m, _cal.monthrange(y, end_m)[1]), "quarter"
    if re.fullmatch(r"\d{4}", s):
        y = int(s)
        return date(y, 1, 1), date(y, 12, 31), "year"
    raise ValueError(s)


def current_quarter(today: date) -> str:
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def policy_note(key: str, today: date) -> str:
    p = POLICY[key]
    tail = (f"（{p['source']}，执行至 {p['valid_until']:%Y-%m-%d}）" if today <= p["valid_until"]
            else f"（{p['source']} 原定执行至 {p['valid_until']:%Y-%m-%d}，**已过期，政策可能已变**）")
    return p["text"] + tail


# ------------------------------------------------------------------ 汇总（OPC-103）
def summary(db: Session, user_id: int, period: str, profile: OpcProfile | None, today: date) -> dict:
    from sqlalchemy import func

    from app.modules.tax.models import TaxWithholding

    start, end, kind = parse_period(period)
    rows = (db.query(OpcEntry).filter(OpcEntry.owner_id == user_id, OpcEntry.occurred_on >= start,
                                      OpcEntry.occurred_on <= end).all())
    income = sum(r.amount_cents for r in rows if r.kind == "income")
    expense = sum(r.amount_cents for r in rows if r.kind == "expense")
    by_cat: dict[tuple[str, str], int] = {}
    for r in rows:
        k = (r.kind, r.category or "未分类")
        by_cat[k] = by_cat.get(k, 0) + r.amount_cents
    from datetime import datetime as _dt
    withheld = (db.query(func.coalesce(func.sum(TaxWithholding.withheld_cents), 0))
                .filter(TaxWithholding.user_id == user_id,
                        TaxWithholding.created_at >= _dt.combine(start, _dt.min.time()),
                        TaxWithholding.created_at < _dt.combine(end + timedelta(days=1), _dt.min.time()))
                .scalar()) or 0
    notes: list[str] = []
    vat_check = None
    p = profile or OpcProfile(user_id=user_id)
    if p.vat == "small_scale":
        span = p.vat_period
        limit = VAT_EXEMPT_CENTS[span]
        # 这一期的销售额：按含税收入估算（申报用的是不含税销售额，这里偏保守）
        if kind == span:
            over = income > limit
            vat_check = {"period_kind": span, "sales_cents": income, "limit_cents": limit, "over": over}
            notes.append(("本期收入超过免税标准：超过部分不再免征，适用 3% 征收率的减按 1%。" if over
                          else "本期收入未超过免税标准。") + "按含税收入估算，申报以不含税销售额为准。" + policy_note("vat_small", today))
        else:
            notes.append(f"你是按{'月' if span == 'month' else '季'}申报的小规模纳税人：看免税标准请选对应的{'月' if span == 'month' else '季度'}。")
    elif p.vat == "general":
        notes.append("一般纳税人按销项减进项计税：收到的专用发票税额要在电子税务局勾选确认。")
    else:
        notes.append("没有登记为纳税人的个人：在平台上收的报酬由平台代扣个税，明细在「我的权益 → 代扣明细」。")
    if p.entity == "company" and p.small_low_profit:
        notes.append(policy_note("small_low_profit", today))
    if p.entity == "sole_prop":
        notes.append(policy_note("sole_prop_iit", today))
    missing = sum(1 for r in rows if r.kind == "expense" and not r.invoice_no)
    if missing:
        notes.append(f"有 {missing} 笔支出没有记发票号：没有发票的支出通常不能在税前扣除，能补开的尽早补开。")
    return {
        "period": period, "start": day(start), "end": day(end), "kind": kind,
        "income_cents": income, "expense_cents": expense, "profit_cents": income - expense,
        "by_category": [{"kind": k, "category": c, "amount_cents": v} for (k, c), v in sorted(by_cat.items())],
        "platform_withheld_cents": int(withheld), "entries": len(rows), "vat_check": vat_check,
        "notes": notes, "disclaimer": DISCLAIMER,
    }


# ------------------------------------------------------------------ 申报日历（OPC-104）
def _shift_weekend(d: date) -> date:
    """周末顺延到周一。法定节假日每年不同，不在这里猜——提示里写「以电子税务局为准」。"""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def deadlines(profile: OpcProfile, today: date, days: int = 120) -> list[dict]:
    """从今天起 `days` 天内的申报与年报节点。只覆盖最常见的几类；口径写在 detail 里。"""
    out: list[dict] = []
    horizon = today + timedelta(days=days)
    note = "截止日遇法定节假日顺延，以电子税务局显示为准"
    for y in (today.year, today.year + 1):
        for mo in range(1, 13):
            d = _shift_weekend(date(y, mo, 15))
            if not (today <= d <= horizon):
                continue
            quarter_start = mo in (1, 4, 7, 10)
            if profile.vat == "small_scale" and (profile.vat_period == "month" or quarter_start):
                out.append({"date": day(d), "kind": "vat",
                            "title": f"申报{'上月' if profile.vat_period == 'month' else '上季度'}增值税及附加税费",
                            "detail": f"小规模纳税人，{note}"})
            if profile.vat == "general":
                out.append({"date": day(d), "kind": "vat", "title": "申报上月增值税及附加税费",
                            "detail": f"一般纳税人按月申报，{note}"})
            if quarter_start and profile.entity == "company":
                out.append({"date": day(d), "kind": "cit", "title": "预缴上季度企业所得税",
                            "detail": f"按季预缴，{note}"})
            if quarter_start and profile.entity == "sole_prop":
                out.append({"date": day(d), "kind": "iit", "title": "预缴上季度经营所得个人所得税",
                            "detail": f"按季预缴，{note}"})
        fixed = []
        if profile.entity == "company":
            fixed.append((date(y, 5, 31), "cit", "企业所得税年度汇算清缴截止", "年度终了之日起五个月内"))
        if profile.entity == "sole_prop":
            fixed.append((date(y, 3, 31), "iit", "经营所得个人所得税年度汇算截止", "取得所得的次年 3 月 31 日前"))
        if profile.entity in ("company", "sole_prop"):
            fixed.append((date(y, 6, 30), "annual", "报送上一年度年度报告（市场监管）", "每年 1 月 1 日至 6 月 30 日，经国家企业信用信息公示系统"))
        if profile.entity == "individual":
            fixed.append((date(y, 6, 30), "iit", "综合所得个人所得税年度汇算截止", "每年 3 月 1 日至 6 月 30 日；平台代扣的劳务报酬也在其中"))
        for d, k, title, detail in fixed:
            if today <= d <= horizon:
                out.append({"date": day(d), "kind": k, "title": title, "detail": detail})
    out.sort(key=lambda x: (x["date"], x["kind"]))
    return out


# ------------------------------------------------------------------ 平台收入导入（OPC-102）
def import_platform(db: Session, user_id: int, since: date | None = None) -> int:
    """把平台上已经到账的报酬记进底稿。按流水 id 去重：导几次都不重复。金额是扣过平台服务费的净额。"""
    from datetime import datetime as _dt

    from app.modules.wallet.models import LedgerEntry

    have = {r for (r,) in db.query(OpcEntry.source_ref).filter(OpcEntry.owner_id == user_id,
                                                                OpcEntry.source_ref.isnot(None))}
    q = db.query(LedgerEntry).filter(LedgerEntry.user_id == user_id, LedgerEntry.kind.in_(PLATFORM_INCOME_KINDS),
                                     LedgerEntry.amount_cents > 0)
    if since:
        q = q.filter(LedgerEntry.created_at >= _dt.combine(since, _dt.min.time()))
    n = 0
    for e in q.order_by(LedgerEntry.id).all():
        ref = f"ledger:{e.id}"
        if ref in have:
            continue
        db.add(OpcEntry(owner_id=user_id, occurred_on=e.created_at.date(), kind="income", amount_cents=e.amount_cents,
                        category="平台收入", counterparty="平台托管放款", note=(e.memo or "")[:100] + "（已扣平台服务费）",
                        source="platform", source_ref=ref))
        n += 1
    return n


# ------------------------------------------------------------------ 合同体检（OPC-105）
CLAUSES = [
    ("payment", "付款方式与时间", r"付款|支付|结算|价款|报酬|费用"),
    ("deadline", "交付期限", r"交付日期|交付时间|期限|工期|截止|完成时间|日前"),
    ("acceptance", "验收标准与期限", r"验收"),
    ("ip", "知识产权归属", r"知识产权|著作权|版权|专利|所有权归"),
    ("breach", "违约责任", r"违约"),
    ("confidential", "保密", r"保密"),
    ("dispute", "争议解决（协商 / 仲裁 / 管辖法院）", r"争议|仲裁|管辖|诉讼"),
    ("termination", "解除与终止", r"解除|终止"),
]


def review_contract(text: str, role: str = "unknown") -> dict:
    """按条款清单与风险句式做体检。只指出「看这里」，不下结论。"""
    findings: list[dict] = []
    for key, name, pat in CLAUSES:
        if not re.search(pat, text):
            findings.append({"level": "high" if key in ("payment", "acceptance", "breach") else "medium", "clause": name,
                             "finding": f"没找到「{name}」相关的约定", "suggestion": f"补一条{name}的约定，写成双方都能核对的句子"})
    risky = [
        (r"无限(连带)?责任|承担[^。；\n]{0,10}(一切|全部)(损失|责任)", "high", "责任上限",
         "约定了没有上限的责任", "约定责任上限（例如不超过合同总额），并排除间接损失"),
        (r"最终解释权", "medium", "解释权", "一方保留最终解释权", "删除或改为「双方协商解释」"),
        (r"自动续(约|期|签)", "medium", "续约", "有自动续约", "写清不续约的通知期限与方式"),
        (r"不可撤销|不得(单方)?解除", "medium", "解除", "限制了解除权", "保留对方严重违约时的解除权"),
        (r"单方(变更|调整|修改)", "medium", "变更", "一方可以单方变更", "改为书面协商一致后变更"),
        (r"竞业|排他|独家", "medium", "排他", "有竞业 / 排他 / 独家约定", "写清范围、期限与对价"),
    ]
    for pat, level, clause, finding, suggestion in risky:
        if re.search(pat, text):
            findings.append({"level": level, "clause": clause, "finding": finding, "suggestion": suggestion})
    if role == "party_b" and re.search(r"(知识产权|著作权|版权)[^。；\n]{0,30}(归|属于)(甲方|委托方|买方)", text) \
            and not re.search(r"付清|支付完毕|全部款项", text):
        findings.append({"level": "high", "clause": "知识产权", "finding": "成果的权利归对方，但没写「付清款项后」才转移",
                         "suggestion": "约定在付清全部款项后转移权利，付清前你保留权利"})
    # 「违约金为合同总额的 50%」与「支付合同总额 50% 的违约金」两种写法都要认
    for m in re.finditer(r"违约金[^。；\n]{0,20}?(\d{1,3})\s*%|(\d{1,3})\s*%[^。；\n]{0,10}违约金", text):
        pct = int(m.group(1) or m.group(2))
        if pct > 30:
            findings.append({"level": "high", "clause": "违约金", "finding": f"违约金比例 {pct}% 偏高",
                             "suggestion": "过高的违约金可以请求适当减少（《民法典》第五百八十五条），签约前就协商降低"})
    for m in re.finditer(r"定金[^。；\n]{0,20}?(\d{1,3})\s*%", text):
        if int(m.group(1)) > 20:
            findings.append({"level": "high", "clause": "定金", "finding": f"定金比例 {m.group(1)}% 超过 20%",
                             "suggestion": "定金不得超过主合同标的额的 20%，超过部分不产生定金效力（《民法典》第五百八十六条）"})
    amounts = re.findall(r"(?:人民币|￥|¥)?\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(?:元|万元)", text)[:10]
    dates = re.findall(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2}", text)[:10]
    order = {"high": 0, "medium": 1, "info": 2}
    findings.sort(key=lambda f: order[f["level"]])
    return {"findings": findings, "amounts": amounts, "dates": dates, "disclaimer": CONTRACT_DISCLAIMER}
