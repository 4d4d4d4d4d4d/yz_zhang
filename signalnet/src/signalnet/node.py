"""节点门面（L3 层）：把身份、内容、PoS、排序、广告、日志组装成一个可运行的节点。

设计要点
- **一切状态变化 = 一条日志事件**。每个写方法先校验、再执行、最后写入哈希链日志；
  `SignalNode.replay` 依次重放事件即可得到完全相同的状态与日志 head（REQ-FD-002）。
- **时间只从参数进入**：所有与时间有关的动作（自动结算、开新轮、复审、托管释放、
  申诉裁定、治理生效、声誉衰减）都由 `tick(now)` 驱动，tick 本身也写入日志。
- **轮次（Round）**：每条内容经历多轮评审——首轮（L0 探索池）、晋级波次、复审、二次机会。
  严格模式下每轮由随机抽签的陪审以 commit-reveal 方式评审（REQ-CS-002/003/005）。

两种配置
- `NodeConfig()`：宽松/仿真模式——开放评审、无需回执、无托管、无邀请门槛，便于实验。
- `NodeConfig.production()`：生产模式——随机陪审 + commit-reveal、签名曝光回执、
  发布质押与配额、7 天托管、邀请注册、新身份权重渐进解锁。

相关需求：REQ-FD-002, REQ-FD-003, REQ-AT-003 ~ REQ-AT-005, REQ-PS-005, REQ-PS-008 ~ REQ-PS-011,
REQ-OR-001 ~ REQ-OR-005, REQ-CS-001 ~ REQ-CS-007, REQ-EV-002 ~ REQ-EV-005, REQ-MT-001 ~ REQ-MT-006,
REQ-ID-003, REQ-CT-004, REQ-RK-006, REQ-AD-006, REQ-AD-007, REQ-GV-001
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from . import (
    ads,
    attestation,
    classify,
    content,
    crypto,
    disputes,
    federation,
    fingerprint,
    governance,
    jury,
    ranking,
    records,
    reputation,
)
from .attestation import CATEGORY_WEIGHTS, Attestation, Commit
from .ledger import Event, Ledger

DAY_S = 86_400


class NodeError(RuntimeError):
    pass


@dataclass
class NodeConfig:
    strict: bool = False  # 随机陪审 + commit-reveal + 签名回执
    # 陪审与轮次
    jury_size: int = 5
    jury_min_rep: int = 20
    jury_min_age_s: int = 0  # 注册满多久才能被抽为陪审（创世身份除外），防止新号直接进陪审团
    round_window_s: int = 72 * 3600  # 一轮评审的总时长（REQ-AT-005）
    commit_window_s: int = 48 * 3600  # 其中前 48h 只收承诺，之后才可揭示（REQ-CS-005）
    min_reveals: int = 1
    # 波次放量（REQ-CS-003）
    wave_caps: tuple[int, ...] = (100, 1_000, 10_000, 100_000)
    promote_threshold: float = 0.7
    bridge_from_level: int = 2
    wave_weights: tuple[int, ...] = (3, 2, 1)
    # 发布质押与配额（REQ-CS-006）
    publish_stake: int = 0
    daily_explore_quota: int = 0  # 0 = 不限
    low_quality: float = 0.3
    # 托管与申诉（REQ-OR-004/005）
    escrow_s: int = 0
    dispute_jury: int = 7
    dispute_window_s: int = 72 * 3600
    dispute_min_votes: int = 1
    dispute_fail_rate: float = 0.5
    copy_extra_slash: int = 20
    report_reward_share: float = 0.5
    # 读者信号（REQ-CS-007）
    reader_min: int = 5
    reader_divergence: float = 0.3
    # 不被时间埋没（REQ-EV-003/004/005）
    explore_ratio: float = 0.1
    revival_ratio: float = 0.05
    revival_min_quality: float = 0.6
    rereview_after_s: tuple[int, ...] = (30 * DAY_S, 180 * DAY_S)
    rereview_drop: float = 0.15
    second_chances: int = 2
    # 母题（REQ-MT-002 ~ 005）
    motif_bits: int = classify.MOTIF_BITS
    motif_burst: int = 5
    motif_window_s: int = 7 * DAY_S
    motif_feed_followers: int = 3
    # 上游分成（REQ-OR-003 / REQ-MT-004）
    derivative_bps: int = 3000
    follower_bps: int = 1000
    # 声誉衰减与新人扶持（REQ-PS-010）
    decay_rate: float = 0.02
    inactive_s: int = 30 * DAY_S
    newcomer_bonus: int = 20
    # 女巫抵抗（REQ-PS-009）
    invite_required: bool = False
    genesis: tuple[str, ...] = ()
    invites_per_day: int = 3
    invite_liability: float = 0.5
    sybil_ramp: int = 1  # 需要多少次“与共识一致”的评审才解锁全部权重；1 = 不限制
    sybil_min: float = 0.25
    # 曝光防作弊（REQ-AD-006）
    fraud_ratio: float = 0.2
    fraud_min_events: int = 10
    # 治理（REQ-GV-001）
    gov_notice_s: int = 7 * DAY_S

    @classmethod
    def production(cls, genesis: tuple[str, ...] = (), **kw: Any) -> NodeConfig:
        base = cls(
            strict=True,
            min_reveals=3,
            publish_stake=5,
            daily_explore_quota=3,
            escrow_s=7 * DAY_S,
            dispute_min_votes=3,
            invite_required=True,
            genesis=tuple(genesis),
            jury_min_age_s=7 * DAY_S,
            sybil_ramp=4,
        )
        return replace(base, **kw)


@dataclass(frozen=True)
class FeedItem:
    kind: str  # organic | explore | revival | motif | ad
    content_id: str
    campaign_id: str = ""
    label: str = ""  # 广告必须带“广告”标签；探索位“新作探索”；复兴位“好作重温”
    members: tuple[str, ...] = ()  # motif：聚合的追随作品


@dataclass
class Round:
    index: int
    kind: str  # wave | rereview | review | second_chance
    level: int
    opened_at: int
    jurors: tuple[str, ...] = ()
    commits: dict[str, Commit] = field(default_factory=dict)
    reveals: list[Attestation] = field(default_factory=list)
    settled: bool = False
    failed: bool = False


@dataclass
class CState:
    received_at: int
    rounds: list[Round] = field(default_factory=list)
    level: int = 0
    status: str = "active"  # active | insufficient | removed
    chances: int = 0
    prior_class: str = "original"
    klass: str = ""
    timely: bool = False
    classic: bool = False
    outdated: bool = False
    superseded_by: str = ""
    stake_locked: int = 0
    explore_ok: bool = True
    first_settled_at: int = -1
    rereviews: int = 0
    review_needed: bool = False
    promoted_pending: bool = False

    @property
    def open_round(self) -> Round | None:
        if self.rounds and not self.rounds[-1].settled and not self.rounds[-1].failed:
            return self.rounds[-1]
        return None


class SignalNode:
    def __init__(
        self,
        node_id: str,
        pos_params: reputation.PoSParams | None = None,
        rank_params: ranking.RankParams | None = None,
        exchange: ads.AdExchange | None = None,
        explore_ratio: float | None = None,
        config: NodeConfig | None = None,
    ) -> None:
        self.config = replace(config) if config else NodeConfig()
        if explore_ratio is not None:
            self.config.explore_ratio = explore_ratio
        if not 0.0 <= self.config.explore_ratio < 1.0:
            raise NodeError("explore_ratio 必须在 [0,1)")
        self.node_id = node_id
        self.ledger = Ledger()
        self.rep = reputation.ReputationBook(pos_params)
        self.rank_params = rank_params or ranking.RankParams()
        self.exchange = exchange or ads.AdExchange()
        self.clock = 0
        # 内容与评审
        self.contents: dict[str, content.Content] = {}
        self.state: dict[str, CState] = {}
        self.attestations: dict[str, list[Attestation]] = {}
        self.settlements: dict[str, reputation.Settlement] = {}
        # 派生状态（由已签名对象确定性计算，重放时自动重建）
        self.fp_index = fingerprint.MultiIndex()
        self.fingerprints: dict[str, int] = {}
        self.media_fps: dict[str, tuple[str, ...]] = {}
        self.near_duplicates: dict[str, str] = {}
        self.motifs = classify.MotifIndex(
            self.config.motif_bits, self.config.motif_burst, self.config.motif_window_s
        )
        self.notifications: dict[str, list[dict[str, str]]] = {}
        # 身份与社交
        self.keys: dict[str, str] = {}  # did -> 当前有效公钥（缺省 = DID 公钥）
        self.key_seq: dict[str, int] = {}
        self.guardians: dict[str, tuple[tuple[str, ...], int]] = {}
        self.recovery_votes: dict[tuple[str, str, int], set[str]] = {}
        self.inviter: dict[str, str] = {}
        self.pending_invites: dict[str, str] = {}
        self.invites_sent: dict[tuple[str, int], int] = {}
        self.follows: dict[str, set[str]] = {}
        self.records_seen: set[str] = set()
        self.my_records: dict[str, list[records.Record]] = {}
        self.aligned_count: dict[str, int] = {}
        self.expertise: dict[str, set[str]] = {}
        self.last_active: dict[str, int] = {}
        self.registered_at: dict[str, int] = {}
        self.reader_signals: dict[str, dict[str, records.Record]] = {}
        self.explore_entries: dict[tuple[str, int], int] = {}
        # 申诉与治理
        self.disputes: dict[str, disputes.Dispute] = {}
        self.proposals: dict[str, governance.Proposal] = {}
        self.params_changed: list[dict[str, Any]] = []
        self.last_decay_day = -1
        self.claims: dict[str, dict[str, Any]] = {}
        # 服务状态（节点本地，非共识，不进入 state_digest）
        self.explore_impressions: dict[str, int] = {}
        self.impressions: dict[str, int] = {}
        self.algorithms: dict[str, ranking.Algorithm] = dict(ranking.BUILTIN_ALGORITHMS)
        self.viewer_algorithm: dict[str, str] = {}
        self.payment_rail: Callable[[str, int], None] | None = None
        self.router = federation.TrafficRouter()

    # ======================================================================
    # 工具
    # ======================================================================
    def _now(self, now: int | None) -> int:
        t = self.clock if now is None else int(now)
        self.clock = max(self.clock, t)
        return t

    def _touch(self, did: str, now: int) -> None:
        self.last_active[did] = max(self.last_active.get(did, 0), now)

    def current_key(self, did: str) -> str:
        return self.keys.get(did, crypto.key_of_did(did))

    def _check_key(self, did: str, key: str) -> None:
        if key != self.current_key(did):
            raise NodeError("签名密钥已失效或未授权（REQ-ID-003）")

    def multiplier(self, did: str) -> float:
        ramp = self.config.sybil_ramp
        if ramp <= 1:
            return 1.0
        return max(self.config.sybil_min, min(1.0, (self.aligned_count.get(did, 0) + 1) / ramp))

    def clusters(self) -> dict[str, str] | None:
        """关注图上的确定性标签传播（REQ-PS-008）。没有关注关系时返回 None。"""
        adj: dict[str, set[str]] = {}
        for a, outs in self.follows.items():
            for b in outs:
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
        if not adj:
            return None
        label = {d: d for d in adj}
        for _ in range(20):
            changed = False
            for d in sorted(adj):
                counts: dict[str, int] = {}
                for nb in adj[d]:
                    counts[label[nb]] = counts.get(label[nb], 0) + 1
                best = max(counts.values())
                new = min(lbl for lbl, c in counts.items() if c == best)
                new = min(new, label[d]) if counts.get(label[d], 0) == best else new
                if new != label[d]:
                    label[d] = new
                    changed = True
            if not changed:
                break
        return label

    # ======================================================================
    # 身份：注册 / 邀请
    # ======================================================================
    def register(self, did: str, now: int | None = None) -> None:
        if not crypto.is_valid_did(did):
            raise NodeError("非法 DID")
        if self.rep.is_registered(did):
            return
        t = self._now(now)
        inviter = self.pending_invites.pop(did, "")
        if self.config.invite_required and not inviter and did not in self.config.genesis:
            raise NodeError("需要邀请才能注册（REQ-PS-009）")
        self.rep.register(did, bonus=self.config.newcomer_bonus)
        if inviter:
            self.inviter[did] = inviter
        self.registered_at[did] = t
        self._touch(did, t)
        self.ledger.append("register", {"did": did, "now": t})

    def _penalize(self, did: str, amount: int) -> int:
        """行为处罚（搬运/作弊），邀请人连带承担一部分（REQ-PS-009）。"""
        got = self.rep.slash(did, amount)
        inv = self.inviter.get(did)
        if inv and got:
            self.rep.slash(inv, int(got * self.config.invite_liability))
        return got

    # ======================================================================
    # 通用签名记录：关注、密钥、邀请、读者信号、申诉、治理、提现
    # ======================================================================
    def submit(self, r: records.Record, now: int | None = None) -> str:
        records.validate(r)
        if r.id in self.records_seen:
            raise NodeError("记录已存在")
        t = self._now(now)
        if r.kind not in ("recover_approve",):
            self._check_key(r.signer, r.key)
        handler = getattr(self, "_rec_" + r.kind, None)
        if handler is None:
            raise NodeError(f"节点不接受记录类型 {r.kind}")
        if r.kind != "invite" and r.kind != "recover_approve":
            self.register(r.signer, t)
        handler(r, t)
        self.records_seen.add(r.id)
        self.my_records.setdefault(r.signer, []).append(r)
        self._touch(r.signer, t)
        self.ledger.append("record", {"record": r.to_dict(), "now": t})
        return r.id

    def _rec_follow(self, r: records.Record, t: int) -> None:
        followee = r.body["followee"]
        if not crypto.is_valid_did(followee) or followee == r.signer:
            raise NodeError("非法关注对象")
        self.follows.setdefault(r.signer, set()).add(followee)

    def _rec_unfollow(self, r: records.Record, t: int) -> None:
        self.follows.get(r.signer, set()).discard(r.body["followee"])

    def _rec_rotate_key(self, r: records.Record, t: int) -> None:
        new_key, seq = r.body["new_key"], int(r.body["seq"])
        if not crypto.is_valid_key(new_key) or seq != self.key_seq.get(r.signer, 0) + 1:
            raise NodeError("非法密钥轮换")
        self.keys[r.signer] = new_key
        self.key_seq[r.signer] = seq

    def _rec_guardians(self, r: records.Record, t: int) -> None:
        gs = tuple(sorted(set(r.body["guardians"])))
        th = int(r.body["threshold"])
        if not gs or not 1 <= th <= len(gs) or r.signer in gs:
            raise NodeError("非法守护人设置")
        self.guardians[r.signer] = (gs, th)

    def _rec_recover_approve(self, r: records.Record, t: int) -> None:
        did, new_key, seq = r.body["did"], r.body["new_key"], int(r.body["seq"])
        self._check_key(r.signer, r.key)
        gs, th = self.guardians.get(did, ((), 0))
        if r.signer not in gs:
            raise NodeError("不是该身份的守护人")
        if seq != self.key_seq.get(did, 0) + 1 or not crypto.is_valid_key(new_key):
            raise NodeError("非法恢复请求")
        votes = self.recovery_votes.setdefault((did, new_key, seq), set())
        votes.add(r.signer)
        if len(votes) >= th:
            self.keys[did] = new_key
            self.key_seq[did] = seq

    def _rec_invite(self, r: records.Record, t: int) -> None:
        invitee = r.body["invitee"]
        if not self.rep.is_registered(r.signer):
            raise NodeError("邀请人尚未注册")
        if not crypto.is_valid_did(invitee) or self.rep.is_registered(invitee):
            raise NodeError("非法被邀请人")
        day = t // DAY_S
        if self.invites_sent.get((r.signer, day), 0) >= self.config.invites_per_day:
            raise NodeError("今日邀请次数已用完")
        if self.rep.balance(r.signer) < self.rep.params.initial_rep // 2:
            raise NodeError("声誉不足，无法邀请")
        self.invites_sent[(r.signer, day)] = self.invites_sent.get((r.signer, day), 0) + 1
        self.pending_invites[invitee] = r.signer

    def _rec_reader_signal(self, r: records.Record, t: int) -> None:
        b = r.body
        cid = b["content_id"]
        if cid not in self.contents:
            raise NodeError("内容不存在")
        if self.contents[cid].author == r.signer:
            raise NodeError("作者不能给自己发读者信号")
        if not 0.0 <= float(b["worth"]) <= 1.0:
            raise NodeError("worth 必须在 [0,1]")
        per = self.reader_signals.setdefault(cid, {})
        if r.signer in per:
            raise NodeError("每位读者对每条内容只能发一次信号")
        per[r.signer] = r

    def _rec_dispute_open(self, r: records.Record, t: int) -> None:
        b = r.body
        kind, target, original, stake = (
            b["kind"],
            b["target"],
            b.get("original", ""),
            int(b["stake"]),
        )
        if kind not in disputes.KINDS or target not in self.contents:
            raise NodeError("非法申诉")
        if kind == "appeal":
            if original not in self.contents or self.contents[original].author != r.signer:
                raise NodeError("只有原作者可以发起原创申诉")
            if self.ledger_pos(original) > self.ledger_pos(target):
                raise NodeError("原作必须早于被申诉内容")
        if self.contents[target].author == r.signer:
            raise NodeError("不能申诉/举报自己的内容")
        try:
            self.rep.lock(r.signer, stake, check_min=False)
        except reputation.ReputationError as e:
            raise NodeError(str(e)) from e
        d = disputes.Dispute(r.id, kind, r.signer, target, original, stake, t)
        parties = {r.signer, self.contents[target].author}
        if original:
            parties.add(self.contents[original].author)
        self.disputes[d.dispute_id] = d  # 严格模式：陪审在下一次 tick 抽签

    def _rec_dispute_vote(self, r: records.Record, t: int) -> None:
        d = self.disputes.get(r.body["dispute_id"])
        if d is None or d.resolved:
            raise NodeError("申诉不存在或已裁定")
        parties = {d.claimant, self.contents[d.target].author}
        if d.original:
            parties.add(self.contents[d.original].author)
        if r.signer in parties:
            raise NodeError("当事人不能投票")
        if self.config.strict and r.signer not in d.jurors:
            raise NodeError("不是本案陪审")
        if r.signer in d.votes:
            raise NodeError("已投票")
        d.votes[r.signer] = (bool(r.body["uphold"]), math.sqrt(max(1, self.rep.balance(r.signer))))

    def _rec_gov_propose(self, r: records.Record, t: int) -> None:
        param, value = r.body["param"], r.body["value"]
        try:
            value = governance.validate_param(param, value)
        except governance.GovernanceError as e:
            raise NodeError(str(e)) from e
        self.proposals[r.id] = governance.Proposal(
            r.id, r.signer, param, value, t, t + self.config.gov_notice_s
        )

    def _rec_gov_vote(self, r: records.Record, t: int) -> None:
        p = self.proposals.get(r.body["proposal_id"])
        if p is None or p.resolved or t >= p.effective_at:
            raise NodeError("提案不存在、已结束或投票期已过")
        p.votes[r.signer] = (bool(r.body["yes"]), math.sqrt(max(1, self.rep.balance(r.signer))))

    def _rec_withdraw(self, r: records.Record, t: int) -> None:
        amount = int(r.body["amount"])
        try:
            self.exchange.withdraw(r.signer, amount)
        except ads.AdError as e:
            raise NodeError(str(e)) from e
        if self.payment_rail is not None:
            self.payment_rail(r.signer, amount)

    def ledger_pos(self, cid: str) -> int:
        return list(self.contents).index(cid)

    # ======================================================================
    # 发布
    # ======================================================================
    def publish(self, c: content.Content, now: int | None = None) -> str:
        content.validate(c)
        if c.id in self.contents:
            raise NodeError("内容已存在")
        t = self._now(c.created_at if now is None else now)
        self.register(c.author, t)
        self._check_key(c.author, c.key)
        for src in c.derived_from:
            if src not in self.contents:
                raise NodeError("衍生来源不存在")
        if c.revises:
            old = self.contents.get(c.revises)
            if old is None or old.author != c.author:
                raise NodeError("只能修订自己已发布的内容")
            if self.state[c.revises].superseded_by:
                raise NodeError("该内容已有修订版本，请修订最新版本")
        st = CState(received_at=t, timely=(c.timeliness == "timely"))
        self._check_duplicate(c, st)
        self._check_motif(c, st, t)
        if c.derived_from and st.prior_class != "copy":
            st.prior_class = "derivative"
        # 发布质押与每日探索配额（REQ-CS-006）
        if self.config.publish_stake:
            try:
                self.rep.lock(c.author, self.config.publish_stake, check_min=False)
                st.stake_locked = self.config.publish_stake
            except reputation.ReputationError:
                st.explore_ok = False
        quota = self.config.daily_explore_quota
        day_key = (c.author, t // DAY_S)
        if quota and self.explore_entries.get(day_key, 0) >= quota:
            st.explore_ok = False
        elif st.explore_ok and c.id not in self.near_duplicates:
            self.explore_entries[day_key] = self.explore_entries.get(day_key, 0) + 1
        if c.revises:
            self.state[c.revises].superseded_by = c.id
        self.contents[c.id] = c
        self.state[c.id] = st
        if not self.config.strict:
            # 严格模式下首轮在下一次 tick 才开轮抽签：抽签种子含发布之后的日志 head，
            # 作者无法通过反复修改内容来“刷”出对自己有利的陪审（REQ-CS-002）
            self._open_round(c.id, "wave", t)
        self._touch(c.author, t)
        self.ledger.append("content", {"content": c.to_dict(), "now": t})
        return c.id

    def _check_duplicate(self, c: content.Content, st: CState) -> None:
        """与其他作者更早发布的原作比对（按日志顺序，不信任自报时间）。REQ-OR-001/008/009"""
        original = ""
        if fingerprint.long_enough(c.body):  # 只用正文：标题改动成本极低，会成为绕过手段
            fp = fingerprint.simhash(c.body)
            for cid in self.fp_index.query(fp):
                if cid in self.near_duplicates or self.contents[cid].author == c.author:
                    continue  # 只与他人原作比对
                original = cid
                break
            self.fingerprints[c.id] = fp
            self.fp_index.add(c.id, fp)
        if not original and c.media_fp:
            for cid, mfp in self.media_fps.items():
                if cid in self.near_duplicates or self.contents[cid].author == c.author:
                    continue
                if fingerprint.media_near_duplicate(c.media_fp, mfp):
                    original = cid
                    break
        if c.media_fp:
            self.media_fps[c.id] = c.media_fp
        if original:
            if original in c.derived_from:
                return  # 声明了衍生关系：不判搬运（REQ-OR-003）
            self.near_duplicates[c.id] = original
            st.prior_class = "copy"
            self.notifications.setdefault(self.contents[original].author, []).append(
                {"kind": "near_duplicate", "copy": c.id, "original": original}
            )

    def _check_motif(self, c: content.Content, st: CState, t: int) -> None:
        if c.id in self.near_duplicates or not fingerprint.long_enough(c.body):
            return
        mid = self.motifs.add(c.id, c.author, self.fingerprints[c.id], t)
        if mid:
            for member in self.motifs.motifs[mid].members:
                if member == mid:
                    continue
                s = self.state.get(member, st)
                if s.prior_class == "original":
                    s.prior_class = "follower"

    def near_duplicate_of(self, content_id: str) -> str | None:
        return self.near_duplicates.get(content_id)

    def motif_of(self, content_id: str) -> str:
        return self.motifs.motif_of.get(content_id, "")

    def explore_eligible(self, content_id: str) -> bool:
        st = self.state.get(content_id)
        if st is None or content_id in self.near_duplicates:
            return False
        return st.explore_ok and st.status == "active" and not st.superseded_by

    # ======================================================================
    # 轮次与陪审
    # ======================================================================
    def _juror_pool(self, exclude: set[str], tags: tuple[str, ...] = ()) -> dict[str, float]:
        pool: dict[str, float] = {}
        cutoff = self.clock - self.config.jury_min_age_s
        for did, bal in self.rep.snapshot().items():
            if did in exclude or bal < self.config.jury_min_rep:
                continue
            if did not in self.config.genesis and self.registered_at.get(did, 0) > cutoff:
                continue
            w = math.sqrt(bal) * self.multiplier(did)
            if tags and self.expertise.get(did, set()) & set(tags):
                w *= 2  # 标签内有可靠评审记录者优先（REQ-CS-002）
            pool[did] = w
        return pool

    def _open_round(self, cid: str, kind: str, t: int) -> Round:
        st = self.state[cid]
        c = self.contents[cid]
        r = Round(len(st.rounds), kind, st.level, t)
        if self.config.strict:
            inv_of_author = self.inviter.get(c.author, "")
            exclude = {c.author, inv_of_author}
            # 作者邀请的人、以及与作者同一邀请人的“兄弟账号”都回避
            exclude |= {
                d
                for d, inv in self.inviter.items()
                if inv == c.author or (inv and inv == inv_of_author)
            }
            exclude |= {a.reviewer for a in self.attestations.get(cid, [])}
            for old in st.rounds:
                exclude |= set(old.jurors)
            seed = jury.seed_for(cid, r.index, self.ledger.head)
            r.jurors = jury.draw(self._juror_pool(exclude, c.tags), self.config.jury_size, seed)
        st.rounds.append(r)
        return r

    def jurors(self, cid: str) -> tuple[str, ...]:
        r = self.state[cid].open_round
        return r.jurors if r else ()

    def _accept_review(self, a: Attestation, t: int) -> tuple[content.Content, CState, Round]:
        attestation.validate(a)
        c = self.contents.get(a.content_id)
        if c is None:
            raise NodeError("内容不存在")
        st = self.state[a.content_id]
        r = st.open_round
        if r is None or r.index != a.round:
            raise NodeError("该轮评审未开放或已结算（评审窗口关闭）")
        if a.reviewer == c.author:
            raise NodeError("作者不得评审自己的内容")
        if any(x.reviewer == a.reviewer for x in self.attestations.get(a.content_id, [])):
            raise NodeError("同一评审者对同一内容只能评审一次")
        if self.config.strict and a.reviewer not in r.jurors:
            raise NodeError("不是本轮抽中的陪审，不能评审（REQ-CS-002）")
        self._check_key(a.reviewer, a.key)
        return c, st, r

    def attest(self, a: Attestation, now: int | None = None) -> None:
        """开放评审（宽松模式）。严格模式必须走 commit → reveal。"""
        if self.config.strict:
            raise NodeError("严格模式下必须使用 commit-reveal（REQ-CS-005）")
        t = self._now(a.created_at if now is None else now)
        _, _st, r = self._accept_review(a, t)
        self.register(a.reviewer, t)
        try:
            self.rep.lock(a.reviewer, a.stake)
        except reputation.ReputationError as e:
            raise NodeError(str(e)) from e
        r.reveals.append(a)
        self.attestations.setdefault(a.content_id, []).append(a)
        self._touch(a.reviewer, t)
        self.ledger.append("attest", {"att": a.to_dict(), "now": t})

    def commit(self, cm: Commit, now: int | None = None) -> None:
        if not cm.verify():
            raise NodeError("commit 签名无效")
        t = self._now(now)
        st = self.state.get(cm.content_id)
        r = st.open_round if st else None
        if r is None or r.index != cm.round:
            raise NodeError("该轮评审未开放")
        if t >= r.opened_at + self.config.commit_window_s:
            raise NodeError("承诺期已结束")
        if self.config.strict and cm.reviewer not in r.jurors:
            raise NodeError("不是本轮抽中的陪审")
        if cm.reviewer in r.commits:
            raise NodeError("已提交承诺")
        self._check_key(cm.reviewer, cm.key)
        r.commits[cm.reviewer] = cm
        self._touch(cm.reviewer, t)
        self.ledger.append("commit", {"commit": cm.to_dict(), "now": t})

    def reveal(self, a: Attestation, salt: str, now: int | None = None) -> None:
        t = self._now(now)
        _, _st, r = self._accept_review(a, t)
        if t < r.opened_at + self.config.commit_window_s:
            raise NodeError("揭示期尚未开始（防止跟风，REQ-CS-005）")
        if t >= r.opened_at + self.config.round_window_s:
            raise NodeError("本轮已截止")
        cm = r.commits.get(a.reviewer)
        if cm is None or not jury.reveal_matches(cm, a, salt):
            raise NodeError("揭示内容与承诺不符")
        try:
            self.rep.lock(a.reviewer, a.stake)
        except reputation.ReputationError as e:
            raise NodeError(str(e)) from e
        r.reveals.append(a)
        self.attestations.setdefault(a.content_id, []).append(a)
        self._touch(a.reviewer, t)
        self.ledger.append("reveal", {"att": a.to_dict(), "salt": salt, "now": t})

    # ======================================================================
    # 结算
    # ======================================================================
    def settle(self, content_id: str, now: int | None = None) -> reputation.Settlement:
        """手动结算当前开放轮（宽松模式/测试）。严格模式由 tick 在截止时自动结算。"""
        st = self.state.get(content_id)
        if st is None:
            raise NodeError("内容不存在")
        r = st.open_round
        if r is None:
            raise NodeError("重复结算：没有开放的评审轮")
        if not r.reveals:
            raise NodeError("没有评审，无法结算")
        t = self._now(now)
        s = self._settle_round(content_id, r, t)
        self.ledger.append("settle", {"content_id": content_id, "now": t})
        return s

    def settle_all(self, now: int | None = None) -> list[reputation.Settlement]:
        out = []
        for cid in sorted(self.state):
            r = self.state[cid].open_round
            if r is not None and r.reveals:
                out.append(self.settle(cid, now))
        return out

    def _votes_weight(self, a: Attestation) -> float:
        return math.sqrt(a.stake) * self.multiplier(a.reviewer)

    def _settle_round(self, cid: str, r: Round, t: int) -> reputation.Settlement:
        c = self.contents[cid]
        st = self.state[cid]
        all_atts = self.attestations.get(cid, [])
        prev = self.settlements.get(cid)
        basis = list(r.reveals) if r.kind == "rereview" else list(all_atts)
        mult = {a.reviewer: self.multiplier(a.reviewer) for a in all_atts}
        s = self.rep.compute(
            basis,
            c.author,
            score_weights=CATEGORY_WEIGHTS[c.category],
            multipliers=mult,
            clusters=self.clusters(),
            reward_for={a.id for a in r.reveals},
        )
        self.rep.apply(s, r.reveals)
        r.settled = True
        for did in s.aligned:
            if did in {a.reviewer for a in r.reveals}:
                self.aligned_count[did] = self.aligned_count.get(did, 0) + 1
                self.expertise.setdefault(did, set()).update(c.tags)

        # 分类（REQ-MT-001）与时效（REQ-EV-002）
        wave_atts = [
            a for a in all_atts if self.state[cid].rounds[a.round].kind != "rereview"
        ] or all_atts
        votes = [(a.klass, self._votes_weight(a)) for a in wave_atts]
        st.klass = classify.classify(votes, st.prior_class, bool(c.derived_from))
        tv = [(a.timely, self._votes_weight(a)) for a in wave_atts if a.timely is not None]
        if tv:
            yes = sum(w for v, w in tv if v)
            st.timely = yes > sum(w for v, w in tv if not v)

        if r.kind == "rereview":  # 时间检验复审（REQ-EV-004）
            st.rereviews += 1
            base = prev.consensus if prev else s.consensus
            if s.consensus >= base - self.config.rereview_drop:
                st.classic = True
            else:
                st.outdated = True
                st.level = max(0, st.level - 1)
            merged = self.rep.compute(
                all_atts,
                c.author,
                score_weights=CATEGORY_WEIGHTS[c.category],
                multipliers=mult,
                clusters=self.clusters(),
                reward_for=set(),
            )
            s = replace(merged, rewards=s.rewards, slashes=s.slashes, author_delta=0)
        if st.klass == "copy":  # 原创性一票否决（REQ-OR-002）
            s = replace(s, consensus=min(s.consensus, classify.COPY_CAP))
            st.status = "removed"
        self.settlements[cid] = s

        first = st.first_settled_at < 0
        if first:
            st.first_settled_at = t
            if st.stake_locked:  # 发布质押：低质罚没，否则解锁（REQ-CS-006）
                self.rep.unlock(c.author, st.stake_locked)
                if s.consensus < self.config.low_quality or st.klass == "copy":
                    self._penalize(c.author, st.stake_locked)
                st.stake_locked = 0
        if st.klass == "copy" and first:
            self._penalize(c.author, self.config.copy_extra_slash)

        # 读者信号背离 → 复审而非晋级（REQ-CS-007）
        st.review_needed = False
        rs = self.reader_score(cid)
        if rs is not None and abs(rs - s.consensus) > self.config.reader_divergence:
            st.review_needed = True
        elif r.kind in ("wave", "second_chance", "review") and st.status == "active":
            need_bridge = st.level + 1 >= self.config.bridge_from_level
            bridged_ok = s.bridged or self.clusters() is None
            if (
                s.consensus >= self.config.promote_threshold
                and st.level < len(self.config.wave_caps)
                and (not need_bridge or bridged_ok)
            ):
                st.level += 1
                st.promoted_pending = st.level < len(self.config.wave_caps)
        return s

    def reader_score(self, cid: str) -> float | None:
        sig = self.reader_signals.get(cid, {})
        if len(sig) < self.config.reader_min:
            return None
        tot = wsum = 0.0
        for did, r in sorted(sig.items()):
            w = math.sqrt(max(1, self.rep.balance(did)))
            b = r.body
            v = (
                0.7 * float(b["worth"])
                + 0.2 * bool(b.get("completed"))
                + 0.1 * bool(b.get("saved"))
            )
            tot += w * v
            wsum += w
        return tot / wsum

    # ======================================================================
    # 时钟：tick 驱动所有与时间有关的动作（REQ-AT-005 等）
    # ======================================================================
    def tick(self, now: int) -> None:
        t = self._now(now)
        cfg = self.config
        for cid in list(self.state):
            st = self.state[cid]
            if not st.rounds and st.status == "active":
                self._open_round(cid, "wave", t)
                continue
            r = st.open_round
            if r is not None and t >= r.opened_at + cfg.round_window_s:
                if len(r.reveals) >= cfg.min_reveals:
                    self._settle_round(cid, r, t)
                else:
                    self._fail_round(cid, st, r, t)
            if st.open_round is None and st.status == "active":
                if st.review_needed:
                    st.review_needed = False
                    self._open_round(cid, "review", t)
                elif st.promoted_pending:
                    st.promoted_pending = False
                    self._open_round(cid, "wave", t)
                elif (
                    st.first_settled_at >= 0
                    and st.rereviews < len(cfg.rereview_after_s)
                    and t >= st.first_settled_at + cfg.rereview_after_s[st.rereviews]
                ):
                    self._open_round(cid, "rereview", t)
        self.exchange.release(t)
        self._resolve_disputes(t)
        self._resolve_proposals(t)
        self._check_fraud(t)
        day = t // DAY_S
        if self.last_decay_day < 0:
            self.last_decay_day = day
        elif day > self.last_decay_day:
            self.last_decay_day = day
            inactive = [d for d, last in self.last_active.items() if last <= t - cfg.inactive_s]
            self.rep.decay(inactive, cfg.decay_rate)
        self.ledger.append("tick", {"now": t})

    def _fail_round(self, cid: str, st: CState, r: Round, t: int) -> None:
        """评审不足：首轮给二次机会（REQ-EV-005），其余轮次直接关闭。"""
        r.failed = True
        for a in r.reveals:
            self.rep.unlock(a.reviewer, a.stake)
        if st.first_settled_at >= 0:
            return
        if st.chances < self.config.second_chances:
            st.chances += 1
            self._open_round(cid, "second_chance", t)
        else:
            st.status = "insufficient"

    def _resolve_disputes(self, t: int) -> None:
        cfg = self.config
        for d in self.disputes.values():
            if d.resolved:
                continue
            if cfg.strict and not d.drawn:
                d.drawn = True
                parties = {d.claimant, self.contents[d.target].author}
                if d.original:
                    parties.add(self.contents[d.original].author)
                seed = jury.seed_for(d.dispute_id, -1, self.ledger.head)
                d.jurors = jury.draw(self._juror_pool(exclude=parties), cfg.dispute_jury, seed)
                continue
            full = cfg.strict and d.jurors and len(d.votes) >= len(d.jurors)
            if not full and t < d.opened_at + cfg.dispute_window_s:
                continue
            d.resolved = True
            d.outcome = disputes.tally(d, cfg.dispute_min_votes)
            self.rep.unlock(d.claimant, d.stake)
            target = self.contents[d.target]
            if d.outcome == "upheld":
                st = self.state[d.target]
                st.klass = "copy"
                st.status = "removed"
                if d.target in self.settlements:
                    s = self.settlements[d.target]
                    self.settlements[d.target] = replace(
                        s, consensus=min(s.consensus, classify.COPY_CAP)
                    )
                if st.stake_locked:
                    self.rep.unlock(target.author, st.stake_locked)
                    st.stake_locked = 0
                slashed = self._penalize(target.author, cfg.copy_extra_slash + cfg.publish_stake)
                to = self.contents[d.original].author if d.original else ads.COMMONS
                self.exchange.redirect_escrow(d.target, to, ("creator", "upstream"))
                if d.kind == "report":
                    self.rep.reward(
                        d.claimant, int(slashed * cfg.report_reward_share) + d.stake // 10
                    )
            elif d.outcome == "rejected":
                self.rep.slash(d.claimant, int(d.stake * cfg.dispute_fail_rate))

    def _resolve_proposals(self, t: int) -> None:
        for p in self.proposals.values():
            if p.resolved or t < p.effective_at:
                continue
            p.resolved = True
            p.passed = governance.passes(p)
            if p.passed:
                try:
                    self._apply_param(p.param, p.value)
                except ads.AdError:
                    p.passed = False  # 与其他参数组合后违反分账约束：不生效
                    continue
                self.params_changed.append({"param": p.param, "value": p.value, "at": t})

    def _apply_param(self, param: str, value: Any) -> None:
        if param in ("explore_ratio", "revival_ratio", "promote_threshold"):
            setattr(self.config, param, value)
        elif param in ("creator_bps", "curators_bps", "node_bps", "commons_bps"):
            cur = asdict(self.exchange.split)
            cur[param] = value
            # 其余比例按差额调整公共池，保证总和 10000；不合法则拒绝生效
            cur["commons_bps"] += 10_000 - sum(cur.values())
            self.exchange.split = ads.RevenueSplit(**cur)
        elif param == "max_hub_share":
            self.router.max_hub_share = value
            self.router.max_total_hub_share = max(self.router.max_total_hub_share, value)

    def _check_fraud(self, t: int) -> None:
        for node_id, (ok, bad) in list(self.exchange.node_traffic.items()):
            total = ok + bad
            if total >= self.config.fraud_min_events and bad / total > self.config.fraud_ratio:
                self.exchange.forfeit_node(node_id)
                self.exchange.node_traffic[node_id] = [0, 0]

    # ======================================================================
    # 广告
    # ======================================================================
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
                "categories": list(c.categories),
                "targeting": c.targeting,
            },
        )

    def curators_for(self, content_id: str) -> dict[str, int]:
        """与共识一致的评审者，按 质押 × 波次权重（首轮 ×3，发现者奖励，REQ-CS-005）。"""
        s = self.settlements.get(content_id)
        if s is None:
            return {}
        aligned = set(s.aligned)
        st = self.state[content_id]
        out: dict[str, int] = {}
        for a in self.attestations.get(content_id, []):
            if a.reviewer in aligned:
                kind = st.rounds[a.round].kind if a.round < len(st.rounds) else "wave"
                ww = (
                    1
                    if kind == "rereview"
                    else jury.wave_weight(
                        sum(1 for x in st.rounds[: a.round] if x.kind != "rereview"),
                        self.config.wave_weights,
                    )
                )
                out[a.reviewer] = a.stake * ww
        return out

    def upstream_for(self, content_id: str) -> dict[str, int]:
        """上游分成：衍生 → 被引用作者；追随 → 母题开创者（REQ-OR-003 / REQ-MT-004）。"""
        c = self.contents[content_id]
        st = self.state[content_id]
        if c.derived_from and st.klass in ("", "derivative"):
            authors = sorted({self.contents[s].author for s in c.derived_from} - {c.author})
            if authors:
                each = self.config.derivative_bps // len(authors)
                return dict.fromkeys(authors, each)
        mid = self.motif_of(content_id)
        if (st.klass or st.prior_class) == "follower" and mid and mid != content_id:
            origin = self.contents[mid].author
            if origin != c.author:
                return {origin: self.config.follower_bps}
        return {}

    def view_ad(
        self,
        viewer: str,
        campaign_id: str,
        content_id: str,
        dwell_ms: int,
        ts: int,
        served_by: str = "",
    ) -> ads.Payout | None:
        """未签名曝光（宽松模式）。严格模式必须提交读者签名回执（REQ-AD-006）。"""
        if self.config.strict:
            raise NodeError("严格模式下曝光必须提交读者签名回执")
        return self._view(viewer, campaign_id, content_id, dwell_ms, ts, served_by, None)

    def view_receipt(self, r: records.Record, now: int | None = None) -> ads.Payout | None:
        records.validate(r)
        if r.kind != "view_receipt":
            raise NodeError("不是曝光回执")
        self._check_key(r.signer, r.key)
        b = r.body
        return self._view(
            r.signer,
            b["campaign_id"],
            b["content_id"],
            int(b["dwell_ms"]),
            int(b["ts"]),
            b.get("node_id", ""),
            r,
        )

    def _view(
        self,
        viewer: str,
        campaign_id: str,
        content_id: str,
        dwell_ms: int,
        ts: int,
        served_by: str,
        receipt: records.Record | None,
    ) -> ads.Payout | None:
        c = self.contents.get(content_id)
        if c is None:
            raise NodeError("内容不存在")
        t = self._now(ts)
        served_by = served_by or self.node_id
        st = self.state[content_id]
        if st.status == "removed":
            return None  # 被判搬运的内容不再产生收益
        view = ads.AdView(viewer, campaign_id, content_id, c.author, served_by, dwell_ms, ts)
        hold = ts + self.config.escrow_s if self.config.escrow_s else 0
        payout = self.exchange.record_view(
            view, self.curators_for(content_id), self.upstream_for(content_id), hold
        )
        data: dict[str, Any] = {
            "viewer": viewer,
            "campaign_id": campaign_id,
            "content_id": content_id,
            "dwell_ms": dwell_ms,
            "ts": ts,
            "served_by": served_by,
            "now": t,
        }
        if receipt is not None:
            data["receipt"] = receipt.to_dict()
        # 可疑流量也要记录（影响节点作弊判定），所以无论是否计费都写日志
        self.ledger.append("ad_view", data)
        return payout

    def statement(self, start: int, end: int) -> dict[str, int]:
        return self.exchange.statement(start, end)

    # ======================================================================
    # 读操作：排序与推荐流
    # ======================================================================
    def rank_inputs(self) -> list[ranking.RankInput]:
        out = []
        for cid, s in self.settlements.items():
            st = self.state[cid]
            if st.status == "removed" or st.superseded_by:
                continue
            c = self.contents[cid]
            prior = None
            if c.revises and c.revises in self.settlements:
                prior = self.settlements[c.revises].consensus
            evidence = s.evidence + (self.rank_params.prior_strength if st.classic else 0.0)
            out.append(
                ranking.RankInput(
                    cid,
                    c.author,
                    s.consensus,
                    s.confidence,
                    c.created_at,
                    evidence,
                    s.agreement,
                    st.timely,
                    prior,
                )
            )
        return out

    def _under_cap(self, cid: str) -> bool:
        lvl = self.state[cid].level
        caps = self.config.wave_caps
        return lvl >= len(caps) or self.impressions.get(cid, 0) < caps[lvl]

    def explore_candidates(self, viewer: str = "") -> list[str]:
        """未结算、具备探索资格的新内容；按 曝光数 × 母题追随序号 升序（REQ-CS-001/MT-005）。"""

        def ordinal(cid: str) -> int:
            mid = self.motif_of(cid)
            return self.motifs.motifs[mid].ordinal(cid) if mid else 1

        cands = [
            cid
            for cid, st in self.state.items()
            if st.first_settled_at < 0 and self.explore_eligible(cid)
        ]
        return sorted(
            cands,
            key=lambda c: (
                (self.explore_impressions.get(c, 0) + 1) * ordinal(c),
                crypto.sha256_hex((viewer + c).encode()),
            ),
        )

    def register_algorithm(self, name: str, fn: ranking.Algorithm) -> None:
        if name in ranking.BUILTIN_ALGORITHMS:
            raise NodeError("不能覆盖内置算法")
        self.algorithms[name] = fn

    def set_algorithm(self, viewer: str, name: str) -> None:
        if name not in self.algorithms:
            raise NodeError(f"未知算法 {name}")
        self.viewer_algorithm[viewer] = name

    def _collapse_motifs(self, ranked: list[str]) -> list[tuple[str, tuple[str, ...]]]:
        """追随作品按母题聚合，一个母题只占一个推荐位（REQ-MT-003）。"""
        out: list[tuple[str, tuple[str, ...]]] = []
        emitted: set[str] = set()
        by_motif: dict[str, list[str]] = {}
        for cid in ranked:
            mid = self.motif_of(cid)
            if mid and (self.state[cid].klass or self.state[cid].prior_class) == "follower":
                by_motif.setdefault(mid, []).append(cid)
        for cid in ranked:
            mid = self.motif_of(cid)
            is_follower = (
                mid and (self.state[cid].klass or self.state[cid].prior_class) == "follower"
            )
            is_origin = mid == cid and by_motif.get(mid)
            if not (is_follower or is_origin):
                out.append((cid, ()))
                continue
            if mid in emitted:
                continue
            emitted.add(mid)
            followers = tuple(by_motif.get(mid, [])[: self.config.motif_feed_followers])
            head = mid if mid in ranked else followers[0]
            out.append((head, tuple(f for f in followers if f != head)))
        return out

    def feed(
        self, now: int, limit: int = 20, viewer: str = "", algorithm: str = ""
    ) -> list[FeedItem]:
        """推荐流 = 自然内容（含母题聚合）+ 探索位 + 复兴位 + 广告位。"""
        cfg = self.config
        name = algorithm or self.viewer_algorithm.get(viewer, "signal")
        inputs = self.rank_inputs()
        ranked = [
            c for c in self.algorithms[name](inputs, now, self.rank_params) if self._under_cap(c)
        ]
        slots = self._collapse_motifs(ranked)
        cands = self.explore_candidates(viewer)
        guaranteed = math.ceil(limit * cfg.explore_ratio) if cfg.explore_ratio > 0 else 0
        backfill = max(0, limit - len(slots)) if cfg.explore_ratio > 0 else 0
        n_explore = min(len(cands), max(guaranteed, backfill))

        # 曝光欠账复兴（REQ-EV-003）
        n_rev_target = math.ceil(limit * cfg.revival_ratio) if cfg.revival_ratio > 0 else 0
        top_ids = {cid for cid, _ in slots[: max(0, limit - n_explore - n_rev_target)]}
        debt = ranking.exposure_debt(inputs, self.impressions, self.rank_params)
        q = {i.content_id: ranking.quality(i, self.rank_params) for i in inputs}
        revival = [
            cid
            for cid, _ in sorted(debt.items(), key=lambda kv: (-kv[1], kv[0]))
            if cid not in top_ids and q[cid] >= cfg.revival_min_quality and self._under_cap(cid)
        ][:n_rev_target]
        n_org = max(0, limit - n_explore - len(revival))
        organic = [s for s in slots if s[0] not in set(revival)][:n_org]
        explore = cands[:n_explore]

        e_int = max(1, round(1 / cfg.explore_ratio)) if cfg.explore_ratio > 0 else 0
        r_int = max(2, round(1 / cfg.revival_ratio)) if cfg.revival_ratio > 0 else 0
        out: list[FeedItem] = []
        oi = ei = ri = 0
        pos = 1
        n_organic_shown = 0
        while oi < len(organic) or ei < len(explore) or ri < len(revival):
            if ei < len(explore) and e_int and pos % e_int == 0:
                pick = "e"
            elif ri < len(revival) and r_int and pos % r_int == r_int // 2:
                pick = "r"
            elif oi < len(organic):
                pick = "o"
            elif ei < len(explore):
                pick = "e"
            else:
                pick = "r"
            if pick == "e":
                cid = explore[ei]
                ei += 1
                self.explore_impressions[cid] = self.explore_impressions.get(cid, 0) + 1
                out.append(FeedItem("explore", cid, label="新作探索"))
            elif pick == "r":
                cid = revival[ri]
                ri += 1
                out.append(FeedItem("revival", cid, label="好作重温"))
            else:
                cid, members = organic[oi]
                oi += 1
                n_organic_shown += 1
                if members or (self.motif_of(cid) and self.motif_of(cid) == cid and members):
                    out.append(FeedItem("motif", cid, members=members, label="母题合集"))
                else:
                    out.append(FeedItem("organic", cid))
                for m in members:
                    self.impressions[m] = self.impressions.get(m, 0) + 1
                if n_organic_shown % self.exchange.slot_interval == 0:
                    camp = self.exchange.select(
                        self.contents[cid].tags, self.contents[cid].category
                    )
                    if camp is not None:
                        out.append(FeedItem("ad", cid, camp.campaign_id, label="广告"))
            self.impressions[cid] = self.impressions.get(cid, 0) + 1
            pos += 1
        return out

    def subscription_feed(self, viewer: str, limit: int = 20) -> list[str]:
        """订阅流：关注作者的内容按发布顺序倒序，不受母题聚合影响（REQ-MT-003）。"""
        followed = self.follows.get(viewer, set())
        ids = [
            cid
            for cid, c in self.contents.items()
            if c.author in followed
            and self.state[cid].status != "removed"
            and not self.state[cid].superseded_by
        ]
        return list(reversed(ids))[:limit]

    def motif_page(self, motif_id: str) -> list[str]:
        m = self.motifs.motifs.get(motif_id)
        if m is None:
            return []
        q = {i.content_id: ranking.quality(i, self.rank_params) for i in self.rank_inputs()}
        rest = sorted((c for c in m.members if c != motif_id), key=lambda c: (-q.get(c, 0.0), c))
        return [motif_id, *rest]

    # ======================================================================
    # 数据可移植（REQ-FD-003）
    # ======================================================================
    def export_bundle(self, did: str) -> dict[str, Any]:
        return {
            "type": "bundle/v1",
            "did": did,
            "key": self.current_key(did),
            "records": [r.to_dict() for r in self.my_records.get(did, [])],
            "contents": [c.to_dict() for c in self.contents.values() if c.author == did],
            "rep_claim": {
                "balance": self.rep.balance(did),
                "ledger_len": len(self.ledger),
                "ledger_head": self.ledger.head,
                "node_id": self.node_id,
            },
        }

    def import_bundle(self, bundle: dict[str, Any], now: int | None = None) -> dict[str, int]:
        """把用户数据迁入本节点：所有对象都重新校验签名后按正常流程写入。"""
        t = self._now(now)
        did = bundle["did"]
        n_rec = n_cont = 0
        recs = [records.Record.from_dict(d) for d in bundle["records"]]
        for r in recs:  # 先导入密钥相关记录，后续对象才能通过新密钥校验
            if r.kind in ("rotate_key", "guardians") and r.id not in self.records_seen:
                self.submit(r, t)
                n_rec += 1
        for d in bundle["contents"]:
            c = content.Content.from_dict(d)
            if c.id not in self.contents and all(s in self.contents for s in c.derived_from):
                self.publish(c, t)
                n_cont += 1
        for r in recs:
            if r.id not in self.records_seen:
                self.submit(r, t)
                n_rec += 1
        claim = dict(bundle["rep_claim"])
        n = claim["ledger_len"]
        evs = list(self.ledger)
        claim["verified"] = n <= len(evs) and n > 0 and evs[n - 1].hash == claim["ledger_head"]
        self.claims[did] = claim
        return {"records": n_rec, "contents": n_cont}

    # ======================================================================
    # 摘要与重放
    # ======================================================================
    def state_digest(self) -> str:
        return crypto.content_hash(
            {
                "rep": self.rep.snapshot(),
                "fund": self.rep.fund,
                "settlements": {
                    cid: [
                        s.consensus,
                        s.confidence,
                        s.author_delta,
                        list(s.aligned),
                        s.evidence,
                        s.agreement,
                        s.bridged,
                    ]
                    for cid, s in sorted(self.settlements.items())
                },
                "states": {
                    cid: [
                        st.level,
                        st.status,
                        st.klass,
                        st.timely,
                        st.classic,
                        st.outdated,
                        len(st.rounds),
                        [list(r.jurors) for r in st.rounds],
                    ]
                    for cid, st in sorted(self.state.items())
                },
                "earnings": dict(sorted(self.exchange.earnings.items())),
                "escrow": self.exchange.escrowed(),
                "paid": dict(sorted(self.exchange.paid.items())),
                "near_duplicates": dict(sorted(self.near_duplicates.items())),
                "motifs": {k: list(v.members) for k, v in sorted(self.motifs.motifs.items())},
                "keys": dict(sorted(self.keys.items())),
                "follows": {k: sorted(v) for k, v in sorted(self.follows.items())},
                "disputes": {k: d.outcome for k, d in sorted(self.disputes.items())},
                "params": self.params_changed,
            }
        )

    def apply_event(self, ev: Event) -> None:
        """按事件类型调用对应写方法（重放与 gossip 同步共用）。"""
        d = ev.data
        now = d.get("now")
        if ev.kind == "register":
            self.register(d["did"], now)
        elif ev.kind == "content":
            self.publish(content.Content.from_dict(d["content"]), now)
        elif ev.kind == "attest":
            self.attest(Attestation.from_dict(d["att"]), now)
        elif ev.kind == "commit":
            self.commit(Commit.from_dict(d["commit"]), now)
        elif ev.kind == "reveal":
            self.reveal(Attestation.from_dict(d["att"]), d["salt"], now)
        elif ev.kind == "settle":
            self.settle(d["content_id"], now)
        elif ev.kind == "tick":
            self.tick(now)
        elif ev.kind == "record":
            self.submit(records.Record.from_dict(d["record"]), now)
        elif ev.kind == "campaign":
            self.add_campaign(
                ads.Campaign(
                    d["campaign_id"],
                    d["advertiser"],
                    d["budget_micros"],
                    d["cpm_micros"],
                    tuple(d["tags"]),
                    categories=tuple(d.get("categories", ())),
                    targeting=dict(d.get("targeting", {})),
                )
            )
        elif ev.kind == "ad_view":
            if "receipt" in d:
                self.view_receipt(records.Record.from_dict(d["receipt"]), now)
            else:
                self._view(
                    d["viewer"],
                    d["campaign_id"],
                    d["content_id"],
                    d["dwell_ms"],
                    d["ts"],
                    d["served_by"],
                    None,
                )
        else:
            raise NodeError(f"未知事件类型 {ev.kind}")

    @classmethod
    def replay(cls, events: Iterable[Event], node_id: str, **kwargs: Any) -> SignalNode:
        node = cls(node_id, **kwargs)
        for ev in events:
            node.apply_event(ev)
        return node
