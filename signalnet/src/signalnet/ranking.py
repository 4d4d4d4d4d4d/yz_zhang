"""开放、可复现的分发排序（L2 层）。

**架构不变量**：本模块禁止导入 `ads`（由 harness 的分层门禁强制），
排序输入中不存在任何“花费/出价”字段——广告预算在结构上无法购买自然流量（REQ-RK-002）。

score   = quality * (1 + fresh_boost * 0.5 ** (age / half_life)) * diversity_penalty
quality = [(E*consensus + n0*prior)/(E+n0) + beta/sqrt(E+n0)] * agreement

- “金子总会发光”：quality 永不衰减，时间只影响有上限的新鲜度加成（REQ-EV-001）。
- 去规模偏置：评审少只代表“不确定”——向先验收缩并获得探索加成，而不是被直接打折；
  评审人数多不再自动换来高分（REQ-CS-004）。

相关需求：REQ-RK-001 ~ REQ-RK-006, REQ-EV-001 ~ REQ-EV-003, REQ-CS-004, REQ-CT-004
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RankInput:
    content_id: str
    author: str
    consensus: float
    confidence: float
    created_at: int
    evidence: float = 0.0  # 评审权重和 E
    agreement: float = 1.0  # 评审一致度
    timely: bool = False  # 时效型内容按乘法衰减（REQ-EV-002）
    prior: float | None = None  # 修订内容继承原内容共识作为先验（REQ-CT-004）


@dataclass(frozen=True)
class RankParams:
    half_life_s: int = 48 * 3600  # 新鲜度加成的半衰期
    fresh_boost: float = 0.5  # 新内容最多获得 +50% 的临时加成（REQ-EV-001）
    same_author_penalty: float = 0.5  # 同一作者第 k 条内容乘以 penalty**k
    min_confidence: float = 0.05  # 置信度过低的内容不进入推荐流（仍可被订阅/搜索）
    min_consensus: float = 0.3  # 共识质量过低的内容不进入推荐流（REQ-RK-005）
    prior: float = 0.5  # 贝叶斯先验均值（REQ-CS-004）
    prior_strength: float = 5.0  # n0：先验相当于多少评审权重
    explore_beta: float = 0.2  # 不确定性探索加成系数


def quality(item: RankInput, p: RankParams) -> float:
    """与时间无关的质量项（REQ-CS-004）。"""
    n = max(0.0, item.evidence) + p.prior_strength
    prior = p.prior if item.prior is None else item.prior
    posterior = (item.evidence * item.consensus + p.prior_strength * prior) / n
    return (posterior + p.explore_beta / n**0.5) * max(0.0, item.agreement)


def base_score(item: RankInput, now: int, p: RankParams) -> float:
    age = max(0, now - item.created_at)
    decay = 0.5 ** (age / p.half_life_s)
    if item.timely:  # 时效型：旧新闻应当退场（REQ-EV-002）
        return quality(item, p) * (1.0 + p.fresh_boost) * decay
    return quality(item, p) * (1.0 + p.fresh_boost * decay)


def rank(items: list[RankInput], now: int, params: RankParams | None = None) -> list[str]:
    """返回排序后的 content_id 列表。确定性：同分按 content_id 升序。"""
    p = params or RankParams()
    eligible = [
        i for i in items if i.confidence >= p.min_confidence and i.consensus >= p.min_consensus
    ]
    pre = sorted(eligible, key=lambda i: (-base_score(i, now, p), i.content_id))
    seen: dict[str, int] = {}
    scored: list[tuple[float, str]] = []
    for it in pre:
        k = seen.get(it.author, 0)
        seen[it.author] = k + 1
        scored.append((base_score(it, now, p) * (p.same_author_penalty**k), it.content_id))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [cid for _, cid in scored]


# ---------------- 可选排序算法（REQ-RK-006） ----------------
# 任何算法只能看到 RankInput（不含任何广告/出价字段），因此第三方算法同样买不到流量。
Algorithm = Callable[[list[RankInput], int, RankParams], list[str]]


def rank_classic(items: list[RankInput], now: int, params: RankParams | None = None) -> list[str]:
    """经典：只看质量，不加新鲜度。"""
    p = params or RankParams()
    eligible = [
        i for i in items if i.confidence >= p.min_confidence and i.consensus >= p.min_consensus
    ]
    return [i.content_id for i in sorted(eligible, key=lambda i: (-quality(i, p), i.content_id))]


def rank_latest(items: list[RankInput], now: int, params: RankParams | None = None) -> list[str]:
    """最新：质量达标的内容按发布时间倒序。"""
    p = params or RankParams()
    eligible = [
        i for i in items if i.confidence >= p.min_confidence and i.consensus >= p.min_consensus
    ]
    return [i.content_id for i in sorted(eligible, key=lambda i: (-i.created_at, i.content_id))]


BUILTIN_ALGORITHMS: dict[str, Algorithm] = {
    "signal": rank,
    "classic": rank_classic,
    "latest": rank_latest,
}


# ---------------- 曝光欠账（REQ-EV-003） ----------------
def exposure_debt(
    items: list[RankInput], impressions: dict[str, int], params: RankParams | None = None
) -> dict[str, float]:
    """欠账 = 同质量档（按 0.1 分档）的中位曝光 − 实际曝光；只返回正欠账。"""
    p = params or RankParams()
    tiers: dict[int, list[int]] = {}
    tier_of: dict[str, int] = {}
    for it in items:
        t = min(9, int(quality(it, p) * 10))
        tier_of[it.content_id] = t
        tiers.setdefault(t, []).append(impressions.get(it.content_id, 0))
    out: dict[str, float] = {}
    for it in items:
        vals = sorted(tiers[tier_of[it.content_id]])
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        debt = median - impressions.get(it.content_id, 0)
        if debt > 0:
            out[it.content_id] = debt
    return out
