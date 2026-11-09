"""广告与收益分配（L2 层）。

商业模式：读者观看广告 → 发布者获得收益。法币记账（micros = 1e-6 货币单位），无代币。

- 有效曝光：停留时长 >= min_dwell_ms，且同一读者/同一广告/同一天去重（REQ-AD-002）。
- 分账比例以基点表示，总和必须为 10000；舍入余数全部进入公共池，保证**分毫不差守恒**（REQ-AD-003）。
- 策展人份额分给对该内容评审“与共识一致”的评审者；无策展人时并入公共池（REQ-AD-004）。
- 广告位与自然内容分离并明确标注，比例有上限（REQ-AD-005）。

相关需求：REQ-AD-001 ~ REQ-AD-005
"""

from __future__ import annotations

from dataclasses import dataclass, field

COMMONS = "commons"  # 公共物品池：协议维护、审核基金、新创作者扶持
DAY_S = 86_400


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


def split_revenue(
    amount: int, creator: str, node_id: str, curators: dict[str, int], split: RevenueSplit
) -> dict[str, int]:
    """curators: {did: 权重(质押量)}。返回 {收款方: micros}，总和恒等于 amount。"""
    shares: dict[str, int] = {}

    def add(k: str, v: int) -> None:
        if v:
            shares[k] = shares.get(k, 0) + v

    add(creator, amount * split.creator_bps // 10_000)
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
    ) -> None:
        if slot_interval < 3:
            raise AdError("广告间隔不得小于 3（每 3 条自然内容最多 1 条广告）")
        self.split = split or RevenueSplit()
        self.min_dwell_ms = min_dwell_ms
        self.slot_interval = slot_interval
        self.campaigns: dict[str, Campaign] = {}
        self.earnings: dict[str, int] = {}
        self._seen: set[tuple[str, str, int]] = set()

    def add_campaign(self, c: Campaign) -> None:
        if c.budget_micros <= 0 or c.price_per_view <= 0:
            raise AdError("预算与单价必须为正")
        self.campaigns[c.campaign_id] = c

    def select(self, tags: tuple[str, ...]) -> Campaign | None:
        """按标签相关度、再按剩余预算选择广告。只决定广告位填充，不影响自然排序。"""
        live = [c for c in self.campaigns.values() if c.remaining >= c.price_per_view]
        if not live:
            return None
        return sorted(
            live, key=lambda c: (-len(set(c.tags) & set(tags)), -c.remaining, c.campaign_id)
        )[0]

    def record_view(self, view: AdView, curators: dict[str, int]) -> Payout | None:
        """返回 None 表示无效曝光（不计费）。"""
        c = self.campaigns.get(view.campaign_id)
        if c is None:
            raise AdError("未知广告")
        if view.dwell_ms < self.min_dwell_ms:
            return None
        if view.viewer == view.creator:
            return None  # 自刷无效
        key = (view.viewer, view.campaign_id, view.ts // DAY_S)
        if key in self._seen:
            return None
        price = c.price_per_view
        if c.remaining < price:
            return None
        self._seen.add(key)
        c.spent_micros += price
        shares = split_revenue(price, view.creator, view.node_id, curators, self.split)
        for k, v in shares.items():
            self.earnings[k] = self.earnings.get(k, 0) + v
        return Payout(view=view, charged=price, shares=shares)

    def total_charged(self) -> int:
        return sum(c.spent_micros for c in self.campaigns.values())
