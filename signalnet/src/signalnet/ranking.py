"""开放、可复现的分发排序（L2 层）。

**架构不变量**：本模块禁止导入 `ads`（由 harness 的分层门禁强制），
排序输入中不存在任何“花费/出价”字段——广告预算在结构上无法购买自然流量（REQ-RK-002）。

score = consensus * confidence * (1 + fresh_boost * 0.5 ** (age / half_life)) * diversity_penalty

“金子总会发光”：质量部分永不衰减，时间只影响有上限的新鲜度加成（REQ-EV-001）。

相关需求：REQ-RK-001 ~ REQ-RK-005, REQ-EV-001
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankInput:
    content_id: str
    author: str
    consensus: float
    confidence: float
    created_at: int


@dataclass(frozen=True)
class RankParams:
    half_life_s: int = 48 * 3600  # 新鲜度加成的半衰期
    fresh_boost: float = 0.5  # 新内容最多获得 +50% 的临时加成（REQ-EV-001）
    same_author_penalty: float = 0.5  # 同一作者第 k 条内容乘以 penalty**k
    min_confidence: float = 0.05  # 置信度过低的内容不进入推荐流（仍可被订阅/搜索）
    min_consensus: float = 0.3  # 共识质量过低的内容不进入推荐流（REQ-RK-005）


def base_score(item: RankInput, now: int, p: RankParams) -> float:
    age = max(0, now - item.created_at)
    freshness = p.fresh_boost * 0.5 ** (age / p.half_life_s)
    return item.consensus * item.confidence * (1.0 + freshness)


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
