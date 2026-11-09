"""节点门面（L3 层）：把身份、内容、PoS、排序、广告、日志组装成一个可运行的节点。

所有状态变化都先校验、再写入哈希链日志；`SignalNode.replay` 可以从日志完全重建状态，
用于跨节点验证（REQ-FD-002）。

相关需求：REQ-FD-002, REQ-AT-003, REQ-AT-004, REQ-PS-005
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from . import ads, attestation, content, crypto, ranking, reputation
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
    ) -> None:
        self.node_id = node_id
        self.ledger = Ledger()
        self.rep = reputation.ReputationBook(pos_params)
        self.rank_params = rank_params or ranking.RankParams()
        self.exchange = exchange or ads.AdExchange()
        self.contents: dict[str, content.Content] = {}
        self.attestations: dict[str, list[attestation.Attestation]] = {}
        self.settlements: dict[str, reputation.Settlement] = {}

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
        self.contents[c.id] = c
        self.ledger.append("content", c.to_dict())
        return c.id

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
            )
            for cid, s in self.settlements.items()
        ]

    def feed(self, now: int, limit: int = 20) -> list[FeedItem]:
        organic = ranking.rank(self.rank_inputs(), now, self.rank_params)[:limit]
        out: list[FeedItem] = []
        for i, cid in enumerate(organic, start=1):
            out.append(FeedItem("organic", cid))
            if i % self.exchange.slot_interval == 0:
                camp = self.exchange.select(self.contents[cid].tags)
                if camp is not None:
                    out.append(FeedItem("ad", cid, camp.campaign_id, label="广告"))
        return out

    def state_digest(self) -> str:
        return crypto.content_hash(
            {
                "rep": self.rep.snapshot(),
                "settlements": {
                    cid: [s.consensus, s.confidence, s.author_delta, list(s.aligned)]
                    for cid, s in sorted(self.settlements.items())
                },
                "earnings": dict(sorted(self.exchange.earnings.items())),
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
