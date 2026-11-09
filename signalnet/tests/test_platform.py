import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from signalnet import ads, attestation, content, crypto, fingerprint, records
from signalnet.api import NodeServer
from signalnet.federation import NodeInfo, TrafficRouter
from signalnet.ledger import LedgerError
from signalnet.node import NodeError, SignalNode
from signalnet.store import SQLiteStore
from signalnet.sync import ForkError, HttpPeer, LocalPeer, SyncError, pull
from tests.helpers import T0, World, body, ident, make_att, make_content

DAY = 86_400


def rec(name, kind, b, **kw):
    return records.sign_record(ident(name), kind, b, **kw)


class TestIdentity(unittest.TestCase):
    def test_key_rotation(self):
        """REQ-ID-003"""
        n = SignalNode("n")
        alice = ident("alice")
        old_post = make_content(author="alice", title="旧密钥发布")
        n.publish(old_post)
        new_key = crypto.Identity.from_seed(b"alice-new-device")
        n.submit(rec("alice", "rotate_key", {"new_key": new_key.public_key_hex, "seq": 1}))
        # 旧内容仍可验证
        self.assertTrue(n.contents[old_post.id].verify())
        # 新内容必须用新钥；旧钥再签无效
        new_post = content.create_content(
            new_key, "新密钥发布", body(1), created_at=T0, ai_generated=False, as_did=alice.did
        )
        n.publish(new_post)
        self.assertEqual(new_post.author, alice.did)
        with self.assertRaises(NodeError):
            n.publish(make_content(author="alice", title="被盗的旧钥"))
        # 重放一致
        self.assertEqual(SignalNode.replay(n.ledger, "b").state_digest(), n.state_digest())

    def test_social_recovery(self):
        """REQ-ID-003"""
        n = SignalNode("n")
        alice = ident("alice")
        n.register(alice.did)
        gs = [ident(f"g{i}").did for i in range(3)]
        n.submit(rec("alice", "guardians", {"guardians": gs, "threshold": 2}))
        rescue = crypto.Identity.from_seed(b"alice-rescue")
        body_ = {"did": alice.did, "new_key": rescue.public_key_hex, "seq": 1}
        n.submit(rec("g0", "recover_approve", body_))
        self.assertEqual(n.current_key(alice.did), crypto.key_of_did(alice.did))  # 未达门限
        with self.assertRaises(NodeError):
            n.submit(rec("stranger", "recover_approve", body_))
        n.submit(rec("g1", "recover_approve", body_))
        self.assertEqual(n.current_key(alice.did), rescue.public_key_hex)


class TestSybil(unittest.TestCase):
    def test_invites_required_and_liability(self):
        """REQ-PS-009"""
        w = World(n_jurors=3)
        stranger = ident("stranger")
        with self.assertRaises(NodeError):
            w.node.register(stranger.did, w.t)
        kids = [w.add(f"kid{i}") for i in range(4)]
        for k in kids[:3]:
            w.record("alice", "invite", {"invitee": k.did})
        with self.assertRaises(NodeError):  # 每日邀请上限
            w.record("alice", "invite", {"invitee": kids[3].did})
        w.node.register(kids[0].did, w.t)
        self.assertEqual(w.node.inviter[kids[0].did], w.ids["alice"].did)
        before = w.node.rep.balance(w.ids["alice"].did)
        w.node._penalize(kids[0].did, 40)
        self.assertEqual(w.node.rep.balance(w.ids["alice"].did), before - 20)  # 连带 50%

    def test_new_identity_weight_ramp(self):
        """REQ-PS-009"""
        w = World(n_jurors=3)
        k = w.add("kid")
        w.record("alice", "invite", {"invitee": k.did})
        w.node.register(k.did, w.t)
        self.assertEqual(w.node.multiplier(k.did), 0.25)
        w.node.aligned_count[k.did] = 3
        self.assertEqual(w.node.multiplier(k.did), 1.0)
        # 批量新号无法左右共识：10 个新号 vs 3 个老评审
        n = SignalNode("n")
        n.config.sybil_ramp = 4
        c = make_content(author="p", title="目标")
        n.publish(c)
        for i in range(3):
            n.aligned_count[ident(f"vet{i}").did] = 5
            n.attest(make_att(f"vet{i}", c.id, 0.2))
        for i in range(8):
            n.attest(make_att(f"sock{i}", c.id, 1.0))
        self.assertLess(n.settle(c.id).consensus, 0.5)


class TestDecay(unittest.TestCase):
    def test_inactive_decay_funds_newcomers(self):
        """REQ-PS-010"""
        n = SignalNode("n")
        rich, active = ident("rich").did, ident("active").did
        n.register(rich, T0)
        n.register(active, T0)
        n.rep._balance[rich] = 1100
        n.rep._balance[active] = 1100
        n.tick(T0)
        n.submit(rec("active", "follow", {"followee": rich}), T0 + 40 * DAY)
        n.tick(T0 + 40 * DAY)
        self.assertEqual(n.rep.balance(rich), 1100 - 20)  # (1100-100)*2%
        self.assertEqual(n.rep.balance(active), 1100)
        self.assertEqual(n.rep.fund, 20)
        n.register(ident("newbie").did, T0 + 41 * DAY)
        self.assertEqual(n.rep.balance(ident("newbie").did), 120)
        self.assertEqual(n.rep.fund, 0)


class TestRevision(unittest.TestCase):
    def test_revision_inherits_prior(self):
        """REQ-CT-004"""
        n = SignalNode("n", explore_ratio=0.0)
        v1 = make_content(author="a", title="初版")
        n.publish(v1)
        for r in ("r1", "r2", "r3"):
            n.attest(make_att(r, v1.id, 0.9))
        n.settle(v1.id)
        v2 = content.create_content(
            ident("a"),
            "勘误版",
            "修正了一个数据",
            created_at=T0 + 10,
            ai_generated=False,
            revises=v1.id,
        )
        n.publish(v2)
        with self.assertRaises(NodeError):  # 只能修订自己的
            n.publish(
                content.create_content(
                    ident("b"), "冒充修订", "x", created_at=T0, ai_generated=False, revises=v2.id
                )
            )
        n.attest(make_att("r9", v2.id, 0.6))
        n.settle(v2.id)  # 单独结算
        inputs = {i.content_id: i for i in n.rank_inputs()}
        self.assertNotIn(v1.id, inputs)  # 旧版被取代
        self.assertEqual(inputs[v2.id].prior, 0.9)  # 继承原内容共识作为先验
        self.assertEqual(n.state[v1.id].superseded_by, v2.id)


class TestPortability(unittest.TestCase):
    def test_export_import(self):
        """REQ-FD-003"""
        a = SignalNode("a")
        alice = ident("alice")
        c = make_content(author="alice", title="我的作品")
        a.publish(c)
        a.submit(rec("alice", "follow", {"followee": ident("bob").did}))
        new_key = crypto.Identity.from_seed(b"alice-2")
        a.submit(rec("alice", "rotate_key", {"new_key": new_key.public_key_hex, "seq": 1}))
        bundle = json.loads(json.dumps(a.export_bundle(alice.did)))  # 可序列化
        b = SignalNode("b")
        b.publish(make_content(author="zed", title="b 节点自己的历史"))  # 日志与 a 不同
        got = b.import_bundle(bundle, T0)
        self.assertEqual(got, {"records": 2, "contents": 1})
        self.assertIn(c.id, b.contents)
        self.assertEqual(b.follows[alice.did], {ident("bob").did})
        self.assertEqual(b.current_key(alice.did), new_key.public_key_hex)
        self.assertFalse(b.claims[alice.did]["verified"])  # b 没有 a 的日志，声誉主张未验证
        # 同步了日志的节点可以验证声誉主张
        c2 = SignalNode.replay(a.ledger, "c")
        c2.import_bundle(bundle, T0)
        self.assertTrue(c2.claims[alice.did]["verified"])


class TestAdsIntegrity(unittest.TestCase):
    def test_signed_receipts_and_node_fraud(self):
        """REQ-AD-006"""
        w = World()
        c = w.publish("alice", body(500))
        w.run_round(c.id, 0.9)
        w.node.add_campaign(ads.Campaign("c", "adv", 10**9, 10**6))
        with self.assertRaises(NodeError):  # 严格模式不接受未签名曝光
            w.node.view_ad(ident("v").did, "c", c.id, 3000, w.t)
        forged = records.Record(
            "view_receipt",
            ident("v").did,
            {
                "campaign_id": "c",
                "content_id": c.id,
                "node_id": "evil",
                "dwell_ms": 3000,
                "ts": w.t,
            },
            "",
            "00" * 64,
        )
        with self.assertRaises(records.RecordError):
            w.node.view_receipt(forged, w.t)
        # 作恶节点：同一读者高频刷曝光
        bot = ident("bot")
        for i in range(80):
            w.node.add_campaign(ads.Campaign(f"x{i}", "adv", 10**9, 10**6))
            r = records.sign_record(
                bot,
                "view_receipt",
                {
                    "campaign_id": f"x{i}",
                    "content_id": c.id,
                    "node_id": "evil",
                    "dwell_ms": 3000,
                    "ts": w.t,
                },
            )
            w.node.view_receipt(r, w.t)
        self.assertEqual(w.node.exchange.node_traffic["evil"], [60, 20])
        held = w.node.exchange.escrowed("node:evil")
        self.assertGreater(held, 0)
        w.tick()
        self.assertEqual(w.node.exchange.escrowed("node:evil"), 0)  # 节点分成被没收
        w.tick(8 * DAY)
        self.assertNotIn("node:evil", w.node.exchange.earnings)
        self.assertTrue(w.node.exchange.reconciles())

    def test_statement_withdraw_reconcile(self):
        """REQ-AD-007"""
        n = SignalNode("n")
        c = make_content(author="alice", title="作品")
        n.publish(c)
        n.add_campaign(ads.Campaign("c", "adv", 10**6, 10**6))
        for i in range(3):
            n.view_ad(ident(f"v{i}").did, "c", c.id, 3000, T0 + i)
        st = n.statement(T0, T0 + 10)
        self.assertEqual(st[c.author], 1800)
        self.assertEqual(sum(st.values()), n.exchange.total_charged())
        paid = []
        n.payment_rail = lambda payee, amt: paid.append((payee, amt))
        n.submit(rec("alice", "withdraw", {"amount": 1000}))
        self.assertEqual(paid, [(c.author, 1000)])
        self.assertEqual(n.exchange.earnings[c.author], 800)
        with self.assertRaises(NodeError):
            n.submit(rec("alice", "withdraw", {"amount": 5000}))
        self.assertTrue(n.exchange.reconciles())

    def test_contextual_targeting_only(self):
        """REQ-AD-008"""
        ads.Campaign("ok", "adv", 100, 1000, targeting={"tags": ["ai"]})
        for bad in ("age", "gender", "location", "user_id", "interests_profile"):
            with self.assertRaises(ads.AdError):
                ads.Campaign("bad", "adv", 100, 1000, targeting={bad: "x"})
        self.assertFalse(
            set(ads.AdView.__dataclass_fields__) & {"age", "gender", "location", "profile"}
        )


class TestFederationMonitor(unittest.TestCase):
    def test_total_hub_share_and_report(self):
        """REQ-FD-004"""
        r = TrafficRouter(max_hub_share=0.2, max_total_hub_share=0.3)
        for i in range(3):
            r.add(NodeInfo(f"hub{i}", "hub", capacity=100))
        for i in range(3):
            r.add(NodeInfo(f"p{i}", "peer"))
        for _ in range(1000):
            r.route()
        rep = r.report()
        self.assertLessEqual(rep["hub_total_share"], 0.3 + 1e-3)
        self.assertEqual(rep["alerts"], [])
        r.served["hub0"] += 10_000  # 模拟异常
        self.assertTrue(r.report()["alerts"])


class TestGovernance(unittest.TestCase):
    def test_notice_period_and_vote(self):
        """REQ-GV-001"""
        n = SignalNode("n")
        pid = n.submit(rec("alice", "gov_propose", {"param": "explore_ratio", "value": 0.2}), T0)
        n.submit(rec("bob", "gov_vote", {"proposal_id": pid, "yes": True}), T0 + 1)
        n.tick(T0 + 6 * DAY)
        self.assertEqual(n.config.explore_ratio, 0.1)  # 公示期未满不生效
        n.tick(T0 + 7 * DAY)
        self.assertEqual(n.config.explore_ratio, 0.2)
        self.assertEqual(n.params_changed[0]["param"], "explore_ratio")
        with self.assertRaises(NodeError):  # 硬边界：创作者分成不得低于 50%
            n.submit(rec("eve", "gov_propose", {"param": "creator_bps", "value": 4000}), T0)
        with self.assertRaises(NodeError):
            n.submit(rec("eve", "gov_propose", {"param": "mint_tokens", "value": 1}), T0)
        # 被否决的提案不生效
        p2 = n.submit(
            rec("alice", "gov_propose", {"param": "revival_ratio", "value": 0.1}), T0 + 8 * DAY
        )
        n.submit(rec("bob", "gov_vote", {"proposal_id": p2, "yes": False}), T0 + 8 * DAY)
        n.tick(T0 + 16 * DAY)
        self.assertEqual(n.config.revival_ratio, 0.05)
        self.assertEqual(SignalNode.replay(n.ledger, "b").state_digest(), n.state_digest())


class TestFingerprintScale(unittest.TestCase):
    def test_media_fingerprint(self):
        """REQ-OR-008"""
        frame = [[(x * 7 + y * 13) % 256 for x in range(64)] for y in range(48)]
        recoded = [[min(255, v + 3) for v in row] for row in frame]  # 重编码/调色
        marked = [row[:] for row in frame]
        for y in range(4):
            for x in range(10):
                marked[y][x] = 255  # 角落水印
        other = [[(x * x + y * 3) % 256 for x in range(64)] for y in range(48)]
        fa = fingerprint.media_fingerprints([frame])
        self.assertTrue(
            fingerprint.media_near_duplicate(fingerprint.media_fingerprints([recoded]), fa)
        )
        self.assertTrue(
            fingerprint.media_near_duplicate(fingerprint.media_fingerprints([marked]), fa)
        )
        self.assertFalse(
            fingerprint.media_near_duplicate(fingerprint.media_fingerprints([other]), fa)
        )
        n = SignalNode("n")
        o = content.create_content(
            ident("a"), "原片", "短", created_at=T0, ai_generated=False, media_fp=fa
        )
        cp = content.create_content(
            ident("b"),
            "搬运",
            "完全不同的文案",
            created_at=T0,
            ai_generated=False,
            media_fp=fingerprint.media_fingerprints([marked]),
        )
        n.publish(o)
        n.publish(cp)
        self.assertEqual(n.near_duplicate_of(cp.id), o.id)

    def test_index_exact_and_fast(self):
        """REQ-OR-009"""
        import random

        rng = random.Random(7)
        idx = fingerprint.MultiIndex()
        fps = [rng.getrandbits(64) for _ in range(20_000)]
        for i, fp in enumerate(fps):
            idx.add(str(i), fp)
        for _ in range(30):  # 召回与线性扫描完全一致
            q = fps[rng.randrange(len(fps))] ^ (1 << rng.randrange(64)) ^ (1 << rng.randrange(64))
            linear = [str(i) for i, fp in enumerate(fps) if fingerprint.distance(q, fp) <= 12]
            self.assertEqual(idx.query(q), linear)
        t0 = time.perf_counter()
        for _ in range(50):
            idx.query(rng.getrandbits(64))
        per_query = (time.perf_counter() - t0) / 50
        self.assertLess(per_query, 0.02)


class TestNetwork(unittest.TestCase):
    def _busy_node(self):
        n = SignalNode("a")
        c = make_content(author="alice", title="作品")
        n.publish(c)
        for r in ("r1", "r2", "r3"):
            n.attest(make_att(r, c.id, 0.8))
        n.settle(c.id)
        n.add_campaign(ads.Campaign("c", "adv", 10**6, 10**6))
        n.view_ad(ident("v").did, "c", c.id, 3000, T0)
        n.tick(T0 + DAY)
        return n, c

    def test_sqlite_restart(self):
        """REQ-NW-002"""
        n, _ = self._busy_node()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "node.db"
            st = SQLiteStore(path)
            self.assertEqual(st.persist(n), len(n.ledger))
            self.assertEqual(st.persist(n), 0)  # 增量
            st.close()
            st2 = SQLiteStore(path)
            m = st2.load()
            self.assertEqual(m.node_id, "a")
            self.assertEqual(m.state_digest(), n.state_digest())
            self.assertEqual(m.ledger.head, n.ledger.head)
            st2.db.execute("UPDATE events SET data = '{}' WHERE seq = 2")
            with self.assertRaises(LedgerError):
                st2.load()
            st2.close()

    def test_gossip_sync(self):
        """REQ-NW-003"""
        a, _ = self._busy_node()
        b = SignalNode("b")
        self.assertEqual(pull(b, LocalPeer(a)), len(a.ledger))
        self.assertEqual(b.state_digest(), a.state_digest())
        a.submit(rec("alice", "follow", {"followee": ident("bob").did}), T0 + 2 * DAY)
        self.assertEqual(pull(b, LocalPeer(a)), 1)  # 增量
        self.assertEqual(pull(b, LocalPeer(a)), 0)
        self.assertEqual(b.state_digest(), a.state_digest())
        # 分叉检测
        b.submit(rec("carol", "follow", {"followee": ident("bob").did}), T0 + 3 * DAY)
        a.submit(rec("dave", "follow", {"followee": ident("bob").did}), T0 + 3 * DAY)
        with self.assertRaises(ForkError):
            pull(b, LocalPeer(a))

        # 伪造的对方状态：事件数据被改过但哈希重算过，重新执行后哈希对不上
        class Liar(LocalPeer):
            def events(self, after):
                evs = super().events(after)
                for e in evs:
                    if e["kind"] == "attest":
                        e["data"]["att"]["stake"] = 1
                return evs

        with self.assertRaises((SyncError, attestation.AttestationError, NodeError)):
            pull(SignalNode("z"), Liar(a))

    def test_http_api(self):
        """REQ-NW-001"""
        n = SignalNode("api")
        with tempfile.TemporaryDirectory() as d:
            store = SQLiteStore(Path(d) / "api.db")
            httpd, url = NodeServer(n, store).serve()
            try:

                def post(path, obj):
                    req = urllib.request.Request(
                        url + path,
                        data=json.dumps(obj).encode(),
                        method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    try:
                        with urllib.request.urlopen(req) as r:
                            return r.status, json.loads(r.read())
                    except urllib.error.HTTPError as e:
                        return e.code, json.loads(e.read())

                def get(path):
                    with urllib.request.urlopen(url + path) as r:
                        return json.loads(r.read())

                c = make_content(author="alice", title="经 API 发布")
                code, out = post("/publish", {"content": c.to_dict(), "now": T0})
                self.assertEqual((code, out["id"]), (200, c.id))
                for r in ("r1", "r2", "r3"):
                    code, _ = post("/attest", {"att": make_att(r, c.id, 0.8).to_dict()})
                    self.assertEqual(code, 200)
                code, out = post("/settle", {"content_id": c.id, "now": T0 + 10})
                self.assertEqual(out["consensus"], 0.8)
                code, out = post("/publish", {"content": c.to_dict()})
                self.assertEqual(code, 400)  # 重复发布
                feed = get(f"/feed?now={T0 + 20}")
                self.assertEqual(feed[0]["content_id"], c.id)
                self.assertEqual(get(f"/content/{c.id}")["level"], 1)
                self.assertEqual(get("/digest")["digest"], n.state_digest())
                self.assertEqual(store.count(), len(n.ledger))  # 每次写入落盘
                # 另一个节点通过 HTTP gossip 同步
                b = SignalNode("b")
                pull(b, HttpPeer(url))
                self.assertEqual(b.state_digest(), n.state_digest())
            finally:
                httpd.shutdown()
                store.close()


if __name__ == "__main__":
    unittest.main()
