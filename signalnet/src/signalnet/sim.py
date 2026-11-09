"""多主体仿真器（L3 层，REQ-SM-001 ~ 003）。

在生产模式节点（随机陪审 + commit-reveal + 托管 + 邀请制）上推进时间，模拟：

| 角色 | 行为 |
|---|---|
| 诚实创作者 | 按潜在质量 q ~ Beta(2,2) 发布原创 |
| 灌水者 | 高频发布低质内容（q < 0.2） |
| 搬运者 | 复制已有高质量内容（改几个字） |
| 潮流开创者 / 追随者 | 带同一新标签、各自拍摄、文案相近 |
| 诚实评审 | 评分 = q + 噪声，能识别搬运/追随 |
| 偷懒评审 | 一律打 0.5，部分承诺后不揭示 |
| 合谋评审 | 给同伙（灌水者）打满分，其余诚实打分以免被罚 |
| 女巫 | 由合谋者邀请的新号，行为同合谋者 |
| 读者 | 刷推荐流、上报曝光、发读者信号、看广告 |

随机数只在本模块使用且种子固定：同一种子两次运行的指标完全相同（REQ-SM-001）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import random
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import ads, attestation, content, crypto, records
from .node import NodeConfig, NodeError, SignalNode

DAY = 86_400
T0 = 1_760_000_000


@dataclass(frozen=True)
class SimConfig:
    seed: int = 7
    days: int = 10
    tick_s: int = 6 * 3600
    creators: int = 30
    creator_posts_per_day: float = 0.5
    spammers: int = 5
    spam_posts_per_day: float = 3.0
    copycats: int = 3
    copy_posts_per_day: float = 0.7
    trend_followers: int = 8
    honest_reviewers: int = 40
    reviewer_noise: float = 0.08
    lazy_reviewers: int = 5
    colluders: int = 5
    sybils_per_colluder: int = 2
    readers: int = 40
    reader_signal_prob: float = 0.25
    ad_view_prob: float = 0.3
    # 被校准的节点参数
    promote_threshold: float = 0.7
    explore_ratio: float = 0.1
    round_window_s: int = 24 * 3600
    jury_size: int = 5
    explore_budget: int = 100
    explore_backfill_max: float = 1.0


# REQ-SM-002 门槛
THRESHOLDS = {
    "quality_exposure_spearman": (">=", 0.6),
    "low_quality_exposure_share": ("<=", 0.10),
    "colluder_vs_honest_rep": ("<", 1.0),
    "copy_detection_rate": (">=", 0.9),
    "newcomer_l2_rate": (">=", 0.5),
}


def check(metrics: dict[str, float]) -> dict[str, bool]:
    out = {}
    for k, (op, v) in THRESHOLDS.items():
        x = metrics[k]
        out[k] = x >= v if op == ">=" else (x <= v if op == "<=" else x < v)
    return out


def _spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    if len(xs) < 3:
        return 0.0
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (sx * sy) if sx and sy else 0.0


@dataclass
class Agent:
    name: str
    role: str
    ident: crypto.Identity
    quality: float = 0.5  # 创作者的平均质量

    @property
    def did(self) -> str:
        return self.ident.did


@dataclass
class Item:
    cid: str
    author: str
    q: float
    kind: str  # original | spam | copy | trend_origin | trend_follower
    t: int


@dataclass
class Sim:
    cfg: SimConfig
    rng: random.Random = field(init=False)
    agents: dict[str, Agent] = field(default_factory=dict)
    items: dict[str, Item] = field(default_factory=dict)
    node: SignalNode = field(init=False)
    pending: dict[tuple[str, int, str], tuple[attestation.Attestation, str]] = field(
        default_factory=dict
    )
    signaled: set[tuple[str, str]] = field(default_factory=set)
    n_text: int = 0

    def __post_init__(self) -> None:
        self.rng = random.Random(self.cfg.seed)
        c = self.cfg

        def mk(prefix: str, role: str, n: int) -> list[Agent]:
            out = []
            for i in range(n):
                name = f"{prefix}{i}"
                a = Agent(name, role, crypto.Identity.from_seed(f"sim:{c.seed}:{name}".encode()))
                self.agents[a.did] = a
                out.append(a)
            return out

        self.creators = mk("creator", "creator", c.creators)
        for a in self.creators:
            a.quality = self.rng.betavariate(2, 2)
        self.spammers = mk("spammer", "spammer", c.spammers)
        self.copycats = mk("copycat", "copycat", c.copycats)
        self.pioneer = mk("pioneer", "creator", 1)[0]
        self.pioneer.quality = 0.8
        self.followers = mk("follower", "follower", c.trend_followers)
        self.honest = mk("honest", "honest", c.honest_reviewers)
        self.lazy = mk("lazy", "lazy", c.lazy_reviewers)
        self.colluders = mk("colluder", "colluder", c.colluders)
        self.readers = mk("reader", "reader", c.readers)
        genesis = tuple(self.agents)
        self.sybils = mk("sybil", "sybil", c.colluders * c.sybils_per_colluder)
        self.ring = {a.did for a in self.spammers + self.colluders + self.sybils}
        cfg = NodeConfig.production(
            genesis=genesis,
            promote_threshold=c.promote_threshold,
            explore_ratio=c.explore_ratio,
            round_window_s=c.round_window_s,
            commit_window_s=c.round_window_s * 2 // 3,
            jury_size=c.jury_size,
            explore_budget=c.explore_budget,
            explore_backfill_max=c.explore_backfill_max,
        )
        self.node = SignalNode("sim", config=cfg)
        for did in genesis:
            self.node.register(did, T0)
        for i, s in enumerate(self.sybils):  # 合谋者邀请女巫
            inviter = self.colluders[i % len(self.colluders)]
            self.node.submit(
                records.sign_record(inviter.ident, "invite", {"invitee": s.did}), T0 + i
            )
            self.node.register(s.did, T0 + i)
        self.node.add_campaign(ads.Campaign("camp", "adv", 10**12, 100_000))

    # ---------------- 文本 ----------------
    def _text(self, n: int = 60) -> str:
        self.n_text += 1
        return "".join(chr(0x4E00 + self.rng.randrange(20_000)) for _ in range(n))

    TREND_WORDS = ("脚开瓶盖", "瓶盖飞出", "脚后跟", "挑战成功", "练了好久")

    def _trend_text(self) -> str:
        words = list(self.TREND_WORDS)
        self.rng.shuffle(words)
        return "，".join(w + self._text(4) for w in words) + self._text(20)

    def _media(self) -> tuple[str, ...]:
        return tuple(f"{self.rng.getrandbits(64):016x}" for _ in range(4))

    # ---------------- 行为 ----------------
    def _publish(self, a: Agent, t: int, kind: str, q: float, **kw: Any) -> None:
        body = kw.pop("body", None) or self._text()
        try:
            c = content.create_content(
                a.ident, f"{kind}-{self.n_text}", body, created_at=t, ai_generated=True, **kw
            )
            self.node.publish(c, t)
        except (NodeError, ValueError):
            return
        self.items[c.id] = Item(c.id, a.did, q, kind, t)

    def _post_prob(self, per_day: float) -> float:
        return min(1.0, per_day * self.cfg.tick_s / DAY)

    def act_creators(self, t: int) -> None:
        c = self.cfg
        for a in self.creators:
            if self.rng.random() < self._post_prob(c.creator_posts_per_day):
                q = min(1.0, max(0.0, self.rng.gauss(a.quality, 0.1)))
                self._publish(a, t, "original", q)
        for a in self.spammers:
            if self.rng.random() < self._post_prob(c.spam_posts_per_day):
                self._publish(a, t, "spam", self.rng.uniform(0.0, 0.2))
        good = [i for i in self.items.values() if i.kind == "original" and i.q >= 0.6]
        for a in self.copycats:
            if good and self.rng.random() < self._post_prob(c.copy_posts_per_day):
                src = self.rng.choice(sorted(good, key=lambda i: i.cid))
                body = self.node.contents[src.cid].body
                pos = self.rng.randrange(len(body) - 3)
                body = body[:pos] + "改两字" + body[pos + 3 :]
                self._publish(a, t, "copy", src.q, body=body)
        day = (t - T0) // DAY
        if day == 1 and not any(i.kind == "trend_origin" for i in self.items.values()):
            self._publish(
                self.pioneer,
                t,
                "trend_origin",
                0.8,
                body=self._trend_text(),
                tags=("脚开瓶盖挑战",),
                media_fp=self._media(),
            )
        if 1 <= day <= 3:
            for a in self.followers:
                done = any(i.author == a.did for i in self.items.values())
                if not done and self.rng.random() < 0.3:
                    self._publish(
                        a,
                        t,
                        "trend_follower",
                        self.rng.uniform(0.4, 0.7),
                        body=self._trend_text(),
                        tags=("脚开瓶盖挑战",),
                        media_fp=self._media(),
                    )

    def _score(self, juror: Agent, item: Item) -> tuple[float, str, float]:
        """返回 (综合分, 分类票, 原创性)。"""
        noise = self.rng.gauss(0, self.cfg.reviewer_noise)
        honest = min(1.0, max(0.0, item.q + noise))
        # 原创性 = 信息增量：灌水内容虽“原创”但没有信息增量，按质量估计
        klass, orig = "original", min(1.0, max(0.0, item.q + self.rng.gauss(0, 0.1)))
        if item.kind == "copy" and self.rng.random() < 0.9:
            klass, orig = "copy", 0.0
        elif item.kind == "trend_follower":
            klass, orig = "follower", 0.3
        if juror.role == "lazy":
            return 0.5, "", 0.5
        if juror.role in ("colluder", "sybil") and item.author in self.ring:
            return 1.0, "original", 1.0
        return honest, klass, orig

    def act_jurors(self, t: int) -> None:
        for cid in sorted(self.node.state):
            info = self.node.current_round(cid)
            if info is None or cid not in self.items:
                continue
            item = self.items[cid]
            for did in info["jurors"]:
                juror = self.agents.get(did)
                if juror is None:
                    continue
                key = (cid, info["index"], did)
                try:
                    if t < info["commit_until"] and key not in self.pending:
                        sc, klass, orig = self._score(juror, item)
                        a = attestation.create_attestation(
                            juror.ident,
                            cid,
                            accuracy=sc,
                            quality=sc,
                            usefulness=sc,
                            originality=orig,
                            klass=klass,
                            stake=8,
                            created_at=t,
                            round=info["index"],
                        )
                        salt = f"{self.rng.getrandbits(64):x}"
                        self.node.commit(attestation.create_commit(juror.ident, a, salt), t)
                        self.pending[key] = (a, salt)
                    elif info["commit_until"] <= t < info["closes_at"] and key in self.pending:
                        a, salt = self.pending.pop(key)
                        if juror.role == "lazy" and self.rng.random() < 0.3:
                            continue  # 占位不评
                        self.node.reveal(a, salt, t)
                except (NodeError, ValueError):
                    self.pending.pop(key, None)

    def act_readers(self, t: int) -> None:
        for r in self.readers:
            feed = self.node.build_feed(t, limit=10, viewer=r.did)
            self.node.record_impressions(feed)
            for f in feed:
                if f.kind == "ad" or f.content_id not in self.items:
                    continue
                item = self.items[f.content_id]
                if (r.did, f.content_id) not in self.signaled and (
                    self.rng.random() < self.cfg.reader_signal_prob
                ):
                    self.signaled.add((r.did, f.content_id))
                    worth = min(1.0, max(0.0, item.q + self.rng.gauss(0, 0.15)))
                    with contextlib.suppress(NodeError, ValueError):
                        self.node.submit(
                            records.sign_record(
                                r.ident,
                                "reader_signal",
                                {
                                    "content_id": f.content_id,
                                    "completed": worth > 0.5,
                                    "saved": worth > 0.8,
                                    "worth": round(worth, 3),
                                },
                            ),
                            t,
                        )
            organic = [f for f in feed if f.kind in ("organic", "motif", "revival")]
            if organic and self.rng.random() < self.cfg.ad_view_prob:
                rec = records.sign_record(
                    r.ident,
                    "view_receipt",
                    {
                        "campaign_id": "camp",
                        "content_id": organic[0].content_id,
                        "node_id": "sim",
                        "dwell_ms": 3000,
                        "ts": t,
                    },
                )
                self.node.view_receipt(rec, t)

    # ---------------- 主循环 ----------------
    def run(self) -> dict[str, Any]:
        end = T0 + self.cfg.days * DAY
        t = T0
        gold_done = False
        while t < end:
            self.act_creators(t)
            self.node.tick(t)
            self.act_jurors(t)
            self.act_readers(t)
            if not gold_done and t >= T0 + 4 * DAY:
                gold_done = self._add_gold(t)
            t += self.cfg.tick_s
        return self.metrics(end)

    def _add_gold(self, t: int) -> bool:
        stable = [
            cid
            for cid, s in sorted(self.node.settlements.items())
            if self.items.get(cid) and self.items[cid].kind == "original" and s.confidence >= 0.3
        ]
        for cid in stable[:3]:
            self.node.add_gold(cid, t)
        return bool(stable)

    def metrics(self, end: int) -> dict[str, Any]:
        n = self.node
        imp = n.impressions
        rated = [i for i in self.items.values() if i.kind in ("original", "spam", "trend_origin")]
        xs = [i.q for i in rated]
        ys = [imp.get(i.cid, 0) / max(1, (end - i.t) / DAY) for i in rated]
        total = sum(imp.get(i.cid, 0) for i in self.items.values()) or 1
        low = sum(imp.get(i.cid, 0) for i in self.items.values() if i.q < 0.3 and i.kind != "copy")
        copies = [i for i in self.items.values() if i.kind == "copy"]
        caught = [
            i
            for i in copies
            if n.near_duplicate_of(i.cid)
            or n.state[i.cid].klass == "copy"
            or n.state[i.cid].status == "removed"
        ]
        cutoff = end - 7 * DAY
        good_new = [
            i for i in self.items.values() if i.kind == "original" and i.q >= 0.75 and i.t <= cutoff
        ]
        reached = [i for i in good_new if n.state[i.cid].level >= 2]

        def avg_rep(agents: list[Agent]) -> float:
            return sum(n.rep.balance(a.did) for a in agents) / max(1, len(agents))

        honest_rep = avg_rep(self.honest)
        earned = n.exchange.statement(T0, end + 1)  # 含托管中的应得收益
        charged = max(1, n.exchange.total_charged())
        creators = {a.did for a in [*self.creators, self.pioneer]}
        followers = [i for i in self.items.values() if i.kind == "trend_follower"]
        m = {
            "contents": len(self.items),
            "quality_exposure_spearman": round(_spearman(xs, ys), 4),
            "low_quality_exposure_share": round(low / total, 4),
            "colluder_vs_honest_rep": round(avg_rep(self.colluders + self.sybils) / honest_rep, 4),
            "copy_detection_rate": round(len(caught) / max(1, len(copies)), 4),
            "newcomer_l2_rate": round(len(reached) / max(1, len(good_new)), 4),
            "honest_rep": round(honest_rep, 2),
            "lazy_rep": round(avg_rep(self.lazy), 2),
            "spam_max_level": max(
                (n.state[i.cid].level for i in self.items.values() if i.kind == "spam"), default=0
            ),
            "followers_in_motif": sum(1 for i in followers if n.motif_of(i.cid)),
            "followers": len(followers),
            "creator_earnings_share": round(
                sum(v for k, v in earned.items() if k in creators) / charged, 4
            ),
            "ring_earnings_share": round(
                sum(v for k, v in earned.items() if k in self.ring) / charged, 4
            ),
            "reconciles": n.exchange.reconciles(),
        }
        m["passes"] = check(m)
        return m


def run(cfg: SimConfig | None = None) -> dict[str, Any]:
    return Sim(cfg or SimConfig()).run()


def sweep(base: SimConfig, grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """参数网格扫描（REQ-SM-003）。"""
    keys = sorted(grid)
    combos: list[dict[str, Any]] = [{}]
    for k in keys:
        combos = [{**c, k: v} for c in combos for v in grid[k]]
    out = []
    for combo in combos:
        m = run(replace(base, **combo))
        out.append({"params": combo, "metrics": m, "all_pass": all(m["passes"].values())})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="signalnet.sim")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--days", type=int, default=SimConfig.days)
    args = ap.parse_args(argv)
    m = run(replace(SimConfig(), seed=args.seed, days=args.days))
    print(
        json.dumps(
            {"config": asdict(replace(SimConfig(), seed=args.seed)), "metrics": m},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
