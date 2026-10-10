"""TAX-002 个税扣缴抽象与三种实现（29 号 spec）。

平台向自然人支付报酬，按《个人所得税法》第九条就是**扣缴义务人**。
应扣未扣的后果不是「以后补上」——《税收征收管理法》第六十九条规定
处应扣未扣税款 50% 到 3 倍的罚款。

按哪种所得课税是**税务与法律决定，不是代码决定**，所以这里三条路都实现，
由 `PLATFORM_TAX_MODE` + `PLATFORM_TAX_PROVIDER` 显式选择，
且生产环境不选就不让启动（TAX-001）。
"""
from dataclasses import dataclass
from typing import Protocol

# 一次支付的扣缴结论
@dataclass(frozen=True)
class TaxAssessment:
    """计税基数、应扣税额与依据。

    `rule` 与 `note` 会落库：口径调整时要能说清**历史每一笔是按什么算的**，
    否则事后自查根本对不上。
    """

    taxable_cents: int
    withheld_cents: int
    rule: str
    note: str


class TaxProvider(Protocol):
    name: str

    def assess(self, income_cents: int, context: dict) -> TaxAssessment: ...


class NoWithholdingTax:
    """路径「不扣」：改造前的行为，诚实命名而不是叫 Default。

    合法的使用场景只有一个：执行方是能自行申报并开票的个体户/企业
    （`PLATFORM_TAX_MODE=self_declared`）。用它来对自然人付款是违法的，
    所以 `tax_mode=none` 在生产会被启动自检拒绝。
    """

    name = "none"

    def assess(self, income_cents: int, context: dict) -> TaxAssessment:
        return TaxAssessment(
            taxable_cents=income_cents, withheld_cents=0, rule="none",
            note="平台未代扣：适用于执行方自行申报纳税并开具发票的情形。",
        )


class LaborIncomeTax:
    """路径 A：劳务报酬所得**预扣预缴**（《个人所得税扣缴申报管理办法》）。

    每次收入 ≤4000 元减除费用 800 元，>4000 元减除 20%；
    预扣率三档：不超过 20000 元 20%；20000~50000 元 30%（速算扣除 2000）；
    超过 50000 元 40%（速算扣除 7000）。

    注意这是**预扣**，不是最终税负——年度汇算时并入综合所得多退少补。
    所以出具给用户的必须叫「代扣明细」，不能叫「完税证明」（TAX-021）。
    """

    name = "labor_income"
    THRESHOLD_CENTS = 400000        # 4000 元
    FLAT_DEDUCTION_CENTS = 80000    # 800 元
    # (应纳税所得额上限, 预扣率 bps, 速算扣除额 分)
    BRACKETS = (
        (2000000, 2000, 0),
        (5000000, 3000, 200000),
        (None, 4000, 700000),
    )

    def assess(self, income_cents: int, context: dict) -> TaxAssessment:
        if income_cents <= 0:
            return TaxAssessment(0, 0, self.name, "收入为零，无需预扣。")
        if income_cents <= self.THRESHOLD_CENTS:
            taxable = max(income_cents - self.FLAT_DEDUCTION_CENTS, 0)
            basis = "≤4000 元，减除费用 800 元"
        else:
            taxable = income_cents * 80 // 100
            basis = ">4000 元，减除 20%"
        for ceiling, rate_bps, quick in self.BRACKETS:
            if ceiling is None or taxable <= ceiling:
                withheld = max(taxable * rate_bps // 10000 - quick, 0)
                return TaxAssessment(
                    taxable_cents=taxable, withheld_cents=withheld, rule=self.name,
                    note=f"劳务报酬预扣预缴：{basis}，预扣率 {rate_bps / 100:.0f}%，"
                         f"速算扣除 {quick / 100:.0f} 元。年度汇算时并入综合所得多退少补。",
                )
        raise AssertionError("unreachable")  # pragma: no cover


class CommissionedCollectionTax:
    """路径 B：经营所得**委托代征**，按核定征收率。

    国内灵活用工平台的主流做法，税负远低于路径 A——但它**依赖一纸
    与税务机关签订的委托代征协议**。没有协议就按这个税率扣，
    是另一种违法（既少扣了税，又无权代征）。所以说明文字里写明了这个前提，
    让任何看到这条记录的人都知道它成立的条件。
    """

    name = "commissioned_collection"

    def __init__(self, rate_bps: int | None = None):
        from app.core.config import settings

        self.rate_bps = settings.TAX_COLLECTION_RATE_BPS if rate_bps is None else rate_bps

    def assess(self, income_cents: int, context: dict) -> TaxAssessment:
        if income_cents <= 0:
            return TaxAssessment(0, 0, self.name, "收入为零，无需代征。")
        withheld = income_cents * self.rate_bps // 10000
        return TaxAssessment(
            taxable_cents=income_cents, withheld_cents=withheld, rule=self.name,
            note=f"经营所得委托代征，核定征收率 {self.rate_bps / 100:.2f}%。"
                 f"⚖️ 本方式以平台与税务机关签订的委托代征协议为前提。",
        )
