"""广告与收益分配（L2 层）。

商业模式：读者观看广告 → 发布者获得收益。法币记账（micros = 1e-6 货币单位），无代币。

- 有效曝光：停留时长 >= min_dwell_ms，且同一读者/同一广告/同一天去重（REQ-AD-002）。
- 分账比例以基点表示，总和必须为 10000；舍入余数全部进入公共池，保证**分毫不差守恒**（REQ-AD-003）。
- 策展人份额分给对该内容评审“与共识一致”的评审者；无策展人时并入公共池（REQ-AD-004）。
- 广告位与自然内容分离并明确标注，比例有上限（REQ-AD-005）。
- 上游分成：衍生内容把创作者份额的 30% 分给被引用作者，追随内容把 10% 分给母题开创者
  （REQ-OR-003, REQ-MT-004）。
- 托管：创作者/上游/节点份额先进入托管期，期满才可提现；申诉成立可转给原作者，
  节点作弊可没收节点份额（REQ-OR-004, REQ-AD-006）。
- 读者频率上限：单读者每小时有效曝光数有上限，超出计为节点可疑流量（REQ-AD-006）。
- 定向只允许标签/品类等上下文字段，不允许任何个人画像字段（REQ-AD-008）。
- 对账：已入账 + 托管中 + 已提现 == 广告扣费总额（REQ-AD-007）。

相关需求：REQ-AD-001 ~ REQ-AD-008, REQ-OR-003, REQ-OR-004, REQ-MT-004
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMMONS = "commons"  # 公共物品池：协议维护、审核基金、新创作者扶持
DAY_S = 86_400
HOUR_S = 3_600
ALLOWED_TARGETING = frozenset({"tags", "categories"})


class AdError(ValueError):
    pass


@dataclass(frozen=True)
class RevenueSplit:
    creator_bps: int = 6000
    curators_bps: int = 1500
    node_bps: int = 1500
    commons_bps: int = 1000

    def __post_init__(self) -> None:
        parts = (self.creator_bps, self.curators_bps, self.node_bps, self.commons_bps)
        if any(x < 0 for x in parts) or sum(parts) != 10_000:
            raise AdError("分账比例必须非负且总和为 10000 bps")
        if self.creator_bps < 5000:
            raise AdError("创作者分成不得低于 50%（愿景约束）")


@dataclass
class Campaign:
    campaign_id: str
    advertiser: str
    budget_micros: int
    cpm_micros: int  # 每千次有效曝光价格
    tags: tuple[str, ...] = ()
    spent_micros: int = 0
    categories: tuple[str, ...] = ()
    targeting: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        bad = set(self.targeting) - ALLOWED_TARGETING
        if bad:
            raise AdError(f"不允许的定向字段 {sorted(bad)}：只能按标签/品类等上下文定向")

    @property
    def price_per_view(self) -> int:
        return self.cpm_micros // 1000

    @property
    def remaining(self) -> int:
        return self.budget_micros - self.spent_micros


@dataclass(frozen=True)
class AdView:
    viewer: str
    campaign_id: str
    content_id: str
    creator: str
    node_id: str
    dwell_ms: int
    ts: int


@dataclass(frozen=True)
class Payout:
    view: AdView
    charged: int
    shares: dict[str, int] = field(default_factory=dict)


@dataclass
class EscrowEntry:
    content_id: str
    payee: str
    amount: int
    release_at: int
    role: str  # creator | upstream | node


def split_revenue(
    amount: int,
    creator: str,
    node_id: str,
    curators: dict[str, int],
    split: RevenueSplit,
    upstream: dict[str, int] | None = None,
) -> dict[str, int]:
    """curators: {did: 权重}；upstream: {did: 占创作者份额的 bps}。总和恒等于 amount。"""
    shares: dict[str, int] = {}

    def add(k: str, v: int) -> None:
        if v:
            shares[k] = shares.get(k, 0) + v

    creator_pool = amount * split.creator_bps // 10_000
    given = 0
    for did in sorted(upstream or {}):
        if did == creator:
            continue
        v = creator_pool * upstream[did] // 10_000  # type: ignore[index]
        add(did, v)
        given += v
    add(creator, creator_pool - given)
    add("node:" + node_id, amount * split.node_bps // 10_000)
    cur_pool = amount * split.curators_bps // 10_000
    total_w = sum(curators.values())
    if total_w > 0:
        for did in sorted(curators):
            add(did, cur_pool * curators[did] // total_w)
    add(COMMONS, amount - sum(shares.values()))  # 余数 + 公共池份额
    return shares


class AdExchange:
    def __init__(
        self,
        split: RevenueSplit | None = None,
        min_dwell_ms: int = 2000,
        slot_interval: int = 5,
        max_views_per_hour: int = 60,
    ) -> None:
        if slot_interval < 3:
            raise AdError("广告间隔不得小于 3（每 3 条自然内容最多 1 条广告）")
        self.split = split or RevenueSplit()
        self.min_dwell_ms = min_dwell_ms
        self.slot_interval = slot_interval
        self.max_views_per_hour = max_views_per_hour
        self.campaigns: dict[str, Campaign] = {}
        self.earnings: dict[str, int] = {}  # 已入账、可提现
        self.escrow: list[EscrowEntry] = []
        self.paid: dict[str, int] = {}  # 已提现
        self.payouts: list[Payout] = []
        self.node_traffic: dict[str, list[int]] = {}  # node -> [有效, 可疑]
        self._seen: set[tuple[str, str, int]] = set()
        self._hourly: dict[tuple[str, int], int] = {}

    def add_campaign(self, c: Campaign) -> None:
        if c.budget_micros <= 0 or c.price_per_view <= 0:
            raise AdError("预算与单价必须为正")
        self.campaigns[c.campaign_id] = c

    def select(self, tags: tuple[str, ...], category: str = "") -> Campaign | None:
        """按上下文（标签/品类）相关度、再按剩余预算选择广告。只决定广告位填充，不影响自然排序。"""
        live = [c for c in self.campaigns.values() if c.remaining >= c.price_per_view]
        if not live:
            return None

        def relevance(c: Campaign) -> int:
            return len(set(c.tags) & set(tags)) + (
                1 if category and category in c.categories else 0
            )

        return sorted(live, key=lambda c: (-relevance(c), -c.remaining, c.campaign_id))[0]

    def _credit(self, payee: str, amount: int) -> None:
        if amount:
            self.earnings[payee] = self.earnings.get(payee, 0) + amount

    def record_view(
        self,
        view: AdView,
        curators: dict[str, int],
        upstream: dict[str, int] | None = None,
        hold_until: int = 0,
    ) -> Payout | None:
        """返回 None 表示无效曝光（不计费）。

        hold_until > view.ts 时，创作者/上游/节点份额进入托管。
        """
        c = self.campaigns.get(view.campaign_id)
        if c is None:
            raise AdError("未知广告")
        if view.dwell_ms < self.min_dwell_ms:
            return None
        if view.viewer == view.creator:
            return None  # 自刷无效
        traffic = self.node_traffic.setdefault(view.node_id, [0, 0])
        hour_key = (view.viewer, view.ts // HOUR_S)
        if self._hourly.get(hour_key, 0) >= self.max_views_per_hour:
            traffic[1] += 1  # 超频：可疑流量，计入服务节点
            return None
        key = (view.viewer, view.campaign_id, view.ts // DAY_S)
        if key in self._seen:
            return None
        price = c.price_per_view
        if c.remaining < price:
            return None
        self._seen.add(key)
        self._hourly[hour_key] = self._hourly.get(hour_key, 0) + 1
        traffic[0] += 1
        c.spent_micros += price
        shares = split_revenue(price, view.creator, view.node_id, curators, self.split, upstream)
        held = {view.creator, "node:" + view.node_id} | set(upstream or {})
        for k, v in shares.items():
            if hold_until > view.ts and k in held:
                role = (
                    "creator"
                    if k == view.creator
                    else ("node" if k.startswith("node:") else "upstream")
                )
                self.escrow.append(EscrowEntry(view.content_id, k, v, hold_until, role))
            else:
                self._credit(k, v)
        p = Payout(view=view, charged=price, shares=shares)
        self.payouts.append(p)
        return p

    # ---- 托管 ----
    def release(self, now: int) -> int:
        keep, moved = [], 0
        for e in self.escrow:
            if e.release_at <= now:
                self._credit(e.payee, e.amount)
                moved += e.amount
            else:
                keep.append(e)
        self.escrow = keep
        return moved

    def redirect_escrow(self, content_id: str, to: str, roles: tuple[str, ...]) -> int:
        """把某内容托管中的指定角色份额转给 to（申诉成立，REQ-OR-004）。"""
        moved = 0
        for e in self.escrow:
            if e.content_id == content_id and e.role in roles:
                e.payee = to
                e.role = "redirected"
                moved += e.amount
        return moved

    def forfeit_node(self, node_id: str) -> int:
        """没收某节点托管中的节点份额到公共池（节点作弊，REQ-AD-006）。"""
        moved = 0
        for e in self.escrow:
            if e.role == "node" and e.payee == "node:" + node_id:
                e.payee = COMMONS
                e.role = "forfeited"
                moved += e.amount
        return moved

    def escrowed(self, payee: str | None = None) -> int:
        return sum(e.amount for e in self.escrow if payee is None or e.payee == payee)

    # ---- 提现与对账（REQ-AD-007） ----
    def withdraw(self, payee: str, amount: int) -> None:
        if amount <= 0 or self.earnings.get(payee, 0) < amount:
            raise AdError("可提现余额不足")
        self.earnings[payee] -= amount
        self.paid[payee] = self.paid.get(payee, 0) + amount

    def statement(self, start: int, end: int) -> dict[str, int]:
        """[start, end) 期间产生的应得收益（含仍在托管中的部分）。"""
        out: dict[str, int] = {}
        for p in self.payouts:
            if start <= p.view.ts < end:
                for k, v in p.shares.items():
                    out[k] = out.get(k, 0) + v
        return dict(sorted(out.items()))

    def total_charged(self) -> int:
        return sum(c.spent_micros for c in self.campaigns.values())

    def reconciles(self) -> bool:
        held = sum(self.earnings.values()) + self.escrowed() + sum(self.paid.values())
        return held == self.total_charged()
