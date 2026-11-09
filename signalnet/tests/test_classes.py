import unittest

from signalnet import ads, classify, content, ranking, records
from signalnet.node import NodeError, SignalNode
from tests.helpers import LONG, T0, World, body, ident, make_att, make_content

DAY = 86_400
# 同一个“玩法”的不同人描述：文本相似但不是逐字搬运
TREND = (
    "用脚开瓶盖挑战：把啤酒瓶放在桌边固定好，抬起脚用脚后跟对准瓶盖边缘，快速向上一踢，"
    "瓶盖就飞出去了。我练了三天终于成功，大家也来试试这个挑战吧。"
)


def trend_variant(i: int) -> str:
    return TREND.replace("三天", f"{i + 2}天").replace(
        "啤酒瓶", ["啤酒瓶", "汽水瓶", "可乐瓶"][i % 3]
    )


def own_video(i: int) -> tuple[str, ...]:
    """每位追随者自己拍的视频：关键帧指纹各不相同。"""
    from signalnet import crypto

    return tuple(crypto.sha256_hex(f"video-{i}-{k}".encode())[:16] for k in range(4))


TREND_TAG = ("脚开瓶盖挑战",)


def post(node, author, text, title="标题", t=T0, **kw):
    c = content.create_content(ident(author), title, text, created_at=t, ai_generated=False, **kw)
    node.publish(c, t)
    return c


def review(node, cid, score, reviewers, klass="", originality=None, timely=None):
    for r in reviewers:
        node.attest(
            make_att_full(r, cid, score, klass=klass, originality=originality, timely=timely)
        )
    return node.settle(cid)


def make_att_full(reviewer, cid, score, stake=10, **kw):
    from signalnet import attestation

    return attestation.create_attestation(
        ident(reviewer),
        cid,
        accuracy=score,
        quality=score,
        usefulness=score,
        stake=stake,
        created_at=T0 + 60,
        **kw,
    )


class TestOriginality(unittest.TestCase):
    def test_copy_veto(self):
        """REQ-OR-002 REQ-MT-001"""
        n = SignalNode("n")
        c = make_content(author="a", title="精致但抄袭")
        n.publish(c)
        s = review(n, c.id, 0.95, ["r1", "r2", "r3"], klass="copy", originality=0.0)
        self.assertLessEqual(s.consensus, classify.COPY_CAP)
        self.assertEqual(n.state[c.id].klass, "copy")
        self.assertNotIn(c.id, [f.content_id for f in n.feed(T0)])
        # 原创性维度参与综合分
        a = make_att_full("r", "x", 1.0, originality=0.0)
        self.assertAlmostEqual(a.score, 0.8)

    def test_derivative_declared_and_split(self):
        """REQ-OR-003"""
        n = SignalNode("n")
        o1 = post(n, "orig1", LONG, title="原作")
        o2 = post(n, "orig2", body(1), title="原作2")
        # 声明衍生：即使与原作近重复也不判搬运
        d = post(
            n, "remixer", LONG + "我的点评：数据很扎实。", title="解读", derived_from=(o1.id, o2.id)
        )
        self.assertIsNone(n.near_duplicate_of(d.id))
        review(n, d.id, 0.8, ["r1", "r2", "r3"], klass="copy")  # copy 票计为 derivative
        self.assertEqual(n.state[d.id].klass, "derivative")
        n.add_campaign(ads.Campaign("c", "adv", 10**6, 10**6))  # 每次 1000 micros
        p = n.view_ad(ident("v").did, "c", d.id, 3000, T0)
        creator_pool = 600
        self.assertEqual(p.shares[o1.author], creator_pool * 1500 // 10_000)
        self.assertEqual(p.shares[o2.author], creator_pool * 1500 // 10_000)
        self.assertEqual(p.shares[d.author], creator_pool - 2 * 90)
        self.assertEqual(sum(p.shares.values()), p.charged)
        with self.assertRaises(NodeError):
            post(n, "x", body(2), derived_from=("不存在",))

    def test_appeal_escrow_redirect(self):
        """REQ-OR-004"""
        w = World()
        orig = w.publish("alice", body(50))
        w.add("thief")
        w.record("j0", "invite", {"invitee": w.ids["thief"].did})
        # 搬运者换了表述，指纹没抓到（模拟洗稿）
        copy = w.publish("thief", body(51), title="洗稿")
        w.run_round(copy.id, 0.8)
        w.node.add_campaign(ads.Campaign("c", "adv", 10**7, 10**6))
        for i in range(5):
            rcpt = records.sign_record(
                ident(f"v{i}"),
                "view_receipt",
                {
                    "campaign_id": "c",
                    "content_id": copy.id,
                    "node_id": "n",
                    "dwell_ms": 3000,
                    "ts": w.t,
                },
            )
            w.node.view_receipt(rcpt, w.t)
        held = w.node.exchange.escrowed(copy.author)
        self.assertEqual(held, 5 * 600)
        self.assertEqual(w.node.exchange.earnings.get(copy.author, 0), 0)
        thief_before = w.node.rep.balance(copy.author)
        did = w.record(
            "alice",
            "dispute_open",
            {"kind": "appeal", "target": copy.id, "original": orig.id, "stake": 10},
        )
        w.tick()  # 抽申诉陪审
        d = w.node.disputes[did]
        self.assertEqual(len(d.jurors), 7)
        self.assertNotIn(orig.author, d.jurors)
        for j in d.jurors:
            w.node.submit(
                records.sign_record(
                    w.by_did[j], "dispute_vote", {"dispute_id": did, "uphold": True}
                ),
                w.t,
            )
        w.tick()
        self.assertEqual(d.outcome, "upheld")
        self.assertEqual(w.node.state[copy.id].status, "removed")
        self.assertLess(w.node.rep.balance(copy.author), thief_before)
        w.tick(8 * DAY)  # 托管期满：钱给原作者而不是搬运者
        self.assertEqual(w.node.exchange.earnings.get(orig.author, 0), held)
        self.assertEqual(w.node.exchange.earnings.get(copy.author, 0), 0)
        self.assertTrue(w.node.exchange.reconciles())

    def test_appeal_rejected_costs_claimant(self):
        """REQ-OR-004"""
        n = SignalNode("n")
        o = post(n, "alice", body(60))
        t = post(n, "bob", body(61))
        did = n.submit(
            records.sign_record(
                ident("alice"),
                "dispute_open",
                {"kind": "appeal", "target": t.id, "original": o.id, "stake": 10},
            ),
            T0,
        )
        for v in ("x1", "x2", "x3"):
            n.submit(
                records.sign_record(ident(v), "dispute_vote", {"dispute_id": did, "uphold": False}),
                T0,
            )
        before = n.rep.balance(ident("alice").did)
        n.tick(T0 + 4 * DAY)
        self.assertEqual(n.disputes[did].outcome, "rejected")
        self.assertEqual(n.rep.balance(ident("alice").did), before - 5)
        with self.assertRaises(NodeError):  # 非原作者不能发起原创申诉
            n.submit(
                records.sign_record(
                    ident("eve"),
                    "dispute_open",
                    {"kind": "appeal", "target": t.id, "original": o.id, "stake": 5},
                ),
                T0,
            )

    def test_report_bounty(self):
        """REQ-OR-005"""
        n = SignalNode("n")
        bad = post(n, "spammer", body(70))
        good_report = n.submit(
            records.sign_record(
                ident("hunter"), "dispute_open", {"kind": "report", "target": bad.id, "stake": 10}
            ),
            T0,
        )
        ok = post(n, "honest", body(71))
        bad_report = n.submit(
            records.sign_record(
                ident("troll"), "dispute_open", {"kind": "report", "target": ok.id, "stake": 10}
            ),
            T0,
        )
        for v in ("x1", "x2", "x3"):
            n.submit(
                records.sign_record(
                    ident(v), "dispute_vote", {"dispute_id": good_report, "uphold": True}
                ),
                T0,
            )
            n.submit(
                records.sign_record(
                    ident(v), "dispute_vote", {"dispute_id": bad_report, "uphold": False}
                ),
                T0,
            )
        n.tick(T0 + 4 * DAY)
        self.assertGreater(n.rep.balance(ident("hunter").did), 100)  # 有效举报获利
        self.assertLess(n.rep.balance(ident("troll").did), 100)  # 恶意举报亏损
        self.assertEqual(n.state[bad.id].status, "removed")


class TestMotif(unittest.TestCase):
    def setUp(self):
        self.n = SignalNode("n", explore_ratio=0.0)
        self.n.config.revival_ratio = 0.0
        self.origin = post(
            self.n, "pioneer", TREND, title="首发", t=T0, tags=TREND_TAG, media_fp=own_video(-1)
        )
        self.followers = [
            post(
                self.n,
                f"fan{i}",
                trend_variant(i),
                title=f"复刻{i}",
                t=T0 + 3600 * (i + 1),
                tags=TREND_TAG,
                media_fp=own_video(i),
            )
            for i in range(8)
        ]

    def test_motif_detected_with_origin(self):
        """REQ-MT-002"""
        mid = self.n.motif_of(self.followers[-1].id)
        self.assertEqual(mid, self.origin.id)
        self.assertEqual(self.n.state[self.followers[0].id].prior_class, "follower")
        self.assertEqual(self.n.state[self.origin.id].prior_class, "original")
        # 文案几乎相同但画面不同：是追随而不是搬运
        self.assertTrue(all(self.n.near_duplicate_of(c.id) is None for c in self.followers))
        # 常态品类：老标签（首次出现早于窗口）即使短期内很多人用也不形成母题
        cook = SignalNode("cook")
        post(cook, "old", body(99), t=T0 - 60 * DAY, tags=("做菜",))
        others = [
            post(cook, f"cook{i}", body(100 + i), title="做菜", t=T0 + i, tags=("做菜",))
            for i in range(6)
        ]
        self.assertTrue(all(cook.motif_of(c.id) == "" for c in others))
        # 新标签但扩散缓慢（超出时间窗口）也不形成母题
        late = SignalNode("late")
        for i in range(5):
            post(late, f"u{i}", body(400 + i), t=T0 + i * 30 * DAY, tags=("慢热话题",))
        self.assertEqual(late.motifs.motifs, {})

    def _settle_all(self, score=0.8):
        for i, c in enumerate([self.origin, *self.followers]):
            review(self.n, c.id, score, [f"r{i}a", f"r{i}b", f"r{i}c"])

    def test_followers_collapsed_one_slot(self):
        """REQ-MT-003"""
        self._settle_all()
        solo = post(self.n, "indie", body(200), title="独立作品")
        review(self.n, solo.id, 0.8, ["s1", "s2", "s3"])
        feed = self.n.feed(T0 + 9 * 3600, limit=20)
        motif_items = [f for f in feed if f.kind == "motif"]
        self.assertEqual(len(motif_items), 1)
        self.assertEqual(motif_items[0].content_id, self.origin.id)
        self.assertEqual(len(motif_items[0].members), 3)
        ids = [f.content_id for f in feed]
        self.assertEqual(sum(1 for c in self.followers if c.id in ids), 0)
        self.assertIn(solo.id, ids)
        # 订阅流与母题合集页不受影响
        self.n.submit(records.sign_record(ident("me"), "follow", {"followee": ident("fan3").did}))
        self.assertEqual(self.n.subscription_feed(ident("me").did), [self.followers[3].id])
        self.assertEqual(len(self.n.motif_page(self.origin.id)), 9)

    def test_follower_revenue_to_origin(self):
        """REQ-MT-004"""
        self._settle_all()
        self.n.add_campaign(ads.Campaign("c", "adv", 10**6, 10**6))
        p = self.n.view_ad(ident("v").did, "c", self.followers[0].id, 3000, T0)
        self.assertEqual(p.shares[self.origin.author], 600 * 1000 // 10_000)
        self.assertEqual(sum(p.shares.values()), p.charged)

    def test_saturation_one_over_n(self):
        """REQ-MT-005"""
        n = SignalNode("sat", explore_ratio=0.5)
        n.config.revival_ratio = 0.0
        post(n, "pioneer", TREND, t=T0, tags=TREND_TAG, media_fp=own_video(-1))
        fs = [
            post(
                n, f"fan{i}", trend_variant(i), t=T0 + i + 1, tags=TREND_TAG, media_fp=own_video(i)
            )
            for i in range(5)
        ]
        for k in range(60):
            n.feed(T0 + 100, limit=2, viewer=f"v{k}")
        counts = [n.explore_impressions.get(c.id, 0) for c in fs]
        self.assertEqual(counts, sorted(counts, reverse=True))  # 越往后越少
        self.assertGreater(counts[0], 2 * counts[-1])

    def test_upgrade_leaves_motif(self):
        """REQ-MT-006"""
        self._settle_all()
        star = self.followers[2]
        self.n.state[star.id].rounds[-1]  # 已结算
        # 新一轮陪审判为“衍生”（有实质增量）
        st = self.n.state[star.id]
        self.n.tick(T0 + 10 * 3600)  # 晋级后开新轮
        self.assertIsNotNone(st.open_round)
        from signalnet import attestation

        for r in ("u1", "u2", "u3", "u4", "u5"):
            self.n.attest(
                attestation.create_attestation(
                    ident(r),
                    star.id,
                    accuracy=0.9,
                    quality=0.9,
                    usefulness=0.9,
                    stake=10,
                    created_at=T0,
                    klass="derivative",
                    round=st.open_round.index,
                )
            )
        self.n.settle(star.id)
        self.assertEqual(st.klass, "derivative")
        feed = self.n.feed(T0 + 11 * 3600, limit=20)
        self.assertIn(star.id, [f.content_id for f in feed if f.kind == "organic"])


class TestTime(unittest.TestCase):
    def test_timely_vs_evergreen(self):
        """REQ-EV-002"""
        n = SignalNode("n")
        news = post(n, "a", body(300), title="新闻", timeliness="timely", category="news")
        guide = post(n, "b", body(301), title="教程", category="tutorial")
        review(n, news.id, 0.9, ["r1", "r2", "r3"])
        review(n, guide.id, 0.9, ["r4", "r5", "r6"])
        self.assertTrue(n.state[news.id].timely)
        later = T0 + 30 * DAY
        inputs = {i.content_id: i for i in n.rank_inputs()}
        p = n.rank_params
        self.assertLess(ranking.base_score(inputs[news.id], later, p), 0.01)  # 旧新闻退场
        self.assertGreater(ranking.base_score(inputs[guide.id], later, p), 0.7)  # 旧教程不退场
        # 陪审可以纠正作者的错误申报
        mis = post(n, "c", body(302), title="伪装常青的热点")
        review(n, mis.id, 0.8, ["r7", "r8", "r9"], timely=True)
        self.assertTrue(n.state[mis.id].timely)

    def test_revival_of_underexposed(self):
        """REQ-EV-003"""
        n = SignalNode("n", explore_ratio=0.0)
        n.config.revival_ratio = 0.1
        items = [make_content(author=f"a{i}", title=f"好作{i}") for i in range(12)]
        for i, c in enumerate(items):
            n.publish(c)
            n.attest(make_att(f"r{i}", c.id, 0.85))
            n.settle(c.id)
        buried = items[-1].id
        for cid in [c.id for c in items[:-1]]:
            n.impressions[cid] = 500
        n.impressions[buried] = 0
        n.rank_params = ranking.RankParams()
        feed = n.feed(T0, limit=5)
        rev = [f for f in feed if f.kind == "revival"]
        self.assertEqual(len(rev), 1)
        self.assertEqual(rev[0].content_id, buried)
        self.assertEqual(rev[0].label, "好作重温")


class TestAlgorithms(unittest.TestCase):
    def test_switchable_algorithms(self):
        """REQ-RK-006"""
        n = SignalNode("n", explore_ratio=0.0)
        n.config.revival_ratio = 0.0
        old = make_content(author="a", title="老而好", created_at=T0)
        new = make_content(author="b", title="新而可", created_at=T0 + 10 * DAY)
        for c, s, rs in ((old, 0.9, ("r1", "r2", "r3")), (new, 0.6, ("r4", "r5", "r6"))):
            n.publish(c)
            for r in rs:
                n.attest(make_att(r, c.id, s))
            n.settle(c.id)
        now = T0 + 10 * DAY
        self.assertEqual([f.content_id for f in n.feed(now, algorithm="latest")], [new.id, old.id])
        self.assertEqual([f.content_id for f in n.feed(now, algorithm="classic")], [old.id, new.id])
        n.register_algorithm(
            "reverse", lambda items, t, p: sorted(i.content_id for i in items)[::-1]
        )
        n.set_algorithm("viewer1", "reverse")
        got = [f.content_id for f in n.feed(now, viewer="viewer1")]
        self.assertEqual(got, sorted([old.id, new.id])[::-1])
        with self.assertRaises(NodeError):
            n.register_algorithm("signal", lambda *a: [])


if __name__ == "__main__":
    unittest.main()
