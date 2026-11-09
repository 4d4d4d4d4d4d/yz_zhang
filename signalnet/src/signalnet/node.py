"""节点门面（L3 层）：把身份、内容、PoS、排序、广告、日志组装成一个可运行的节点。

所有状态变化都先校验、再写入哈希链日志；`SignalNode.replay` 可以从日志完全重建状态，
用于跨节点验证（REQ-FD-002）。

相关需求：REQ-FD-002, REQ-AT-003, REQ-AT-004, REQ-PS-005, REQ-OR-001, REQ-CS-001
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from . import ads, attestation, content, crypto, fingerprint, ranking, reputation
from .ledger import Event, Ledger


class NodeError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeedItem:
    kind: str  # "organic" | "ad"
    content_id: str
    campaign_id: str = ""
    label: str = ""  # 广告必须带“广告”标签


class SignalNode:
    def __init__(
        self,
        node_id: str,
        pos_params: reputation.PoSParams | None = None,
        rank_params: ranking.RankParams | None = None,
        exchange: ads.AdExchange | None = None,
        explore_ratio: float = 0.1,
    ) -> None:
        if not 0.0 <= explore_ratio < 1.0:
            raise NodeError("explore_ratio 必须在 [0,1)")
        self.explore_ratio = explore_ratio
        self.node_id = node_id
        self.ledger = Ledger()
        self.rep = reputation.ReputationBook(pos_params)
        self.rank_params = rank_params or ranking.RankParams()
        self.exchange = exchange or ads.AdExchange()
        self.contents: dict[str, content.Content] = {}
        self.attestations: dict[str, list[attestation.Attestation]] = {}
        self.settlements: dict[str, reputation.Settlement] = {}
        # 派生状态（由已签名内容确定性计算，重放时自动重建，不单独写日志）
        self.fingerprints: dict[str, int] = {}
        self.near_duplicates: dict[str, str] = {}  # 近重复内容 ID -> 更早的原作 ID
        self.notifications: dict[str, list[dict[str, str]]] = {}
        # 服务状态（节点本地，非共识，不进入 state_digest）
        self.explore_impressions: dict[str, int] = {}

    # ---------- 写操作 ----------
    def register(self, did: str) -> None:
        if not crypto.is_valid_did(did):
            raise NodeError("非法 DID")
        if not self.rep.is_registered(did):
            self.rep.register(did)
            self.ledger.append("register", {"did": did})

    def publish(self, c: content.Content) -> str:
        content.validate(c)
        if c.id in self.contents:
            raise NodeError("内容已存在")
        self.register(c.author)
        self._check_duplicate(c)
        self.contents[c.id] = c
        self.ledger.append("content", c.to_dict())
        return c.id

    def _check_duplicate(self, c: content.Content) -> None:
        """与其他作者更早发布的内容比对（按日志顺序，不信任自报时间）。REQ-OR-001"""
        text = (
            c.body
        )  # 只用正文：标题短且改动成本极低，纳入标题会成为绕过手段（实测改标题+调序距离升到 14）
        if not fingerprint.long_enough(text):
            return
        fp = fingerprint.simhash(text)
        for cid, other_fp in self.fingerprints.items():  # dict 保持插入顺序 = 日志顺序
            if cid in self.near_duplicates:
                continue  # 只与原作比对：否则作者重发自己的作品会被判为“抄袭了抄袭者”
            original = self.contents[cid]
            if original.author != c.author and fingerprint.is_near_duplicate(fp, other_fp):
                self.near_duplicates[c.id] = cid
                self.notifications.setdefault(original.author, []).append(
                    {"kind": "near_duplicate", "copy": c.id, "original": cid}
                )
                break
        self.fingerprints[c.id] = fp
        # 线性扫描仅适用于 M1；规模化见 REQ-OR-009（LSH 分桶索引）

    def near_duplicate_of(self, content_id: str) -> str | None:
        return self.near_duplicates.get(content_id)

    def explore_eligible(self, content_id: str) -> bool:
        """是否具备探索池资格（探索池本身见 REQ-CS-001）。"""
        return content_id in self.contents and content_id not in self.near_duplicates

    def attest(self, a: attestation.Attestation) -> None:
        attestation.validate(a)
        c = self.contents.get(a.content_id)
        if c is None:
            raise NodeError("内容不存在")
        if a.content_id in self.settlements:
            raise NodeError("内容已结算，评审窗口关闭")
        if a.reviewer == c.author:
            raise NodeError("作者不得评审自己的内容")
        existing = self.attestations.setdefault(a.content_id, [])
        if any(x.reviewer == a.reviewer for x in existing):
            raise NodeError("同一评审者对同一内容只能评审一次")
        self.register(a.reviewer)
        try:
            self.rep.lock(a.reviewer, a.stake)
        except reputation.ReputationError as e:
            raise NodeError(str(e)) from e
        existing.append(a)
        self.ledger.append("attest", a.to_dict())

    def settle(self, content_id: str) -> reputation.Settlement:
        if content_id in self.settlements:
            raise NodeError("重复结算")
        atts = self.attestations.get(content_id, [])
        if not atts:
            raise NodeError("没有评审，无法结算")
        s = self.rep.compute(atts, self.contents[content_id].author)
        self.rep.apply(s, atts)
        self.settlements[content_id] = s
        self.ledger.append("settle", {"content_id": content_id})
        return s

    def settle_all(self) -> list[reputation.Settlement]:
        out = []
        for cid in sorted(self.attestations):
            if cid not in self.settlements and self.attestations[cid]:
                out.append(self.settle(cid))
        return out

    def add_campaign(self, c: ads.Campaign) -> None:
        self.exchange.add_campaign(c)
        self.ledger.append(
            "campaign",
            {
                "campaign_id": c.campaign_id,
                "advertiser": c.advertiser,
                "budget_micros": c.budget_micros,
                "cpm_micros": c.cpm_micros,
                "tags": list(c.tags),
            },
        )

    def curators_for(self, content_id: str) -> dict[str, int]:
        s = self.settlements.get(content_id)
        if s is None:
            return {}
        aligned = set(s.aligned)
        return {
            a.reviewer: a.stake
            for a in self.attestations.get(content_id, [])
            if a.reviewer in aligned
        }

    def view_ad(
        self,
        viewer: str,
        campaign_id: str,
        content_id: str,
        dwell_ms: int,
        ts: int,
        served_by: str = "",
    ) -> ads.Payout | None:
        c = self.contents.get(content_id)
        if c is None:
            raise NodeError("内容不存在")
        served_by = served_by or self.node_id
        view = ads.AdView(viewer, campaign_id, content_id, c.author, served_by, dwell_ms, ts)
        payout = self.exchange.record_view(view, self.curators_for(content_id))
        if payout is not None:
            self.ledger.append(
                "ad_view",
                {
                    "viewer": viewer,
                    "campaign_id": campaign_id,
                    "content_id": content_id,
                    "dwell_ms": dwell_ms,
                    "ts": ts,
                    "served_by": served_by,
                },
            )
        return payout

    # ---------- 读操作 ----------
    def rank_inputs(self) -> list[ranking.RankInput]:
        return [
            ranking.RankInput(
                cid,
                self.contents[cid].author,
                s.consensus,
                s.confidence,
                self.contents[cid].created_at,
                s.evidence,
                s.agreement,
            )
            for cid, s in self.settlements.items()
        ]

    def explore_candidates(self, viewer: str = "") -> list[str]:
        """未结算、具备探索资格的新内容；曝光最少者优先，同数按 sha256(viewer+id) 打散。"""
        cands = [
            cid
            for cid in self.contents
            if cid not in self.settlements and self.explore_eligible(cid)
        ]
        return sorted(
            cands,
            key=lambda c: (
                self.explore_impressions.get(c, 0),
                crypto.sha256_hex((viewer + c).encode()),
            ),
        )

    def feed(self, now: int, limit: int = 20, viewer: str = "") -> list[FeedItem]:
        """推荐流 = 自然内容 + 探索位（REQ-CS-001）+ 广告位（REQ-AD-005）。"""
        ranked = ranking.rank(self.rank_inputs(), now, self.rank_params)
        cands = self.explore_candidates(viewer)
        guaranteed = math.ceil(limit * self.explore_ratio) if self.explore_ratio > 0 else 0
        backfill = max(0, limit - len(ranked)) if self.explore_ratio > 0 else 0
        n_explore = min(len(cands), max(guaranteed, backfill))
        organic = ranked[: limit - n_explore]
        explore = cands[:n_explore]
        for cid in explore:
            self.explore_impressions[cid] = self.explore_impressions.get(cid, 0) + 1
        interval = max(1, round(1 / self.explore_ratio)) if self.explore_ratio > 0 else 0

        out: list[FeedItem] = []
        oi = ei = 0
        pos = 1  # 只计自然位和探索位，广告位另计
        while oi < len(organic) or ei < len(explore):
            take_explore = ei < len(explore) and (oi >= len(organic) or pos % interval == 0)
            if take_explore:
                out.append(FeedItem("explore", explore[ei], label="新作探索"))
                ei += 1
            else:
                cid = organic[oi]
                oi += 1
                out.append(FeedItem("organic", cid))
                if oi % self.exchange.slot_interval == 0:
                    camp = self.exchange.select(self.contents[cid].tags)
                    if camp is not None:
                        out.append(FeedItem("ad", cid, camp.campaign_id, label="广告"))
            pos += 1
        return out

    def state_digest(self) -> str:
        return crypto.content_hash(
            {
                "rep": self.rep.snapshot(),
                "settlements": {
                    cid: [
                        s.consensus,
                        s.confidence,
                        s.author_delta,
                        list(s.aligned),
                        s.evidence,
                        s.agreement,
                    ]
                    for cid, s in sorted(self.settlements.items())
                },
                "earnings": dict(sorted(self.exchange.earnings.items())),
                "near_duplicates": dict(sorted(self.near_duplicates.items())),
            }
        )

    # ---------- 重放验证 ----------
    @classmethod
    def replay(cls, events: Iterable[Event], node_id: str, **kwargs: object) -> SignalNode:
        node = cls(node_id, **kwargs)  # type: ignore[arg-type]
        for ev in events:
            d = ev.data
            if ev.kind == "register":
                node.register(d["did"])
            elif ev.kind == "content":
                node.publish(content.Content.from_dict(d))
            elif ev.kind == "attest":
                node.attest(attestation.Attestation.from_dict(d))
            elif ev.kind == "settle":
                node.settle(d["content_id"])
            elif ev.kind == "campaign":
                node.add_campaign(
                    ads.Campaign(
                        d["campaign_id"],
                        d["advertiser"],
                        d["budget_micros"],
                        d["cpm_micros"],
                        tuple(d["tags"]),
                    )
                )
            elif ev.kind == "ad_view":
                node.view_ad(
                    d["viewer"],
                    d["campaign_id"],
                    d["content_id"],
                    d["dwell_ms"],
                    d["ts"],
                    served_by=d["served_by"],
                )
            else:
                raise NodeError(f"未知事件类型 {ev.kind}")
        return node
