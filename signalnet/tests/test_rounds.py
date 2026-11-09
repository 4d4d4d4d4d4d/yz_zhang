import itertools
import unittest

from signalnet import attestation, jury, records
from signalnet.node import NodeError, SignalNode
from tests.helpers import T0, World, body, ident, make_att, make_content

DAY = 86_400


class TestJury(unittest.TestCase):
    def test_random_jury_deterministic_and_enforced(self):
        """REQ-CS-002"""
        w = World()
        c = w.publish("alice", body(1))
        self.assertEqual(w.node.jurors(c.id), ())  # 发布时不抽签：防止作者刷陪审
        w.tick()
        js = w.node.jurors(c.id)
        self.assertEqual(len(js), 3)
        self.assertNotIn(c.author, js)
        # 任意节点重放可复算同一抽签结果
        replica = SignalNode.replay(w.node.ledger, "b", config=w.config)
        self.assertEqual(replica.jurors(c.id), js)
        # 非抽中者不能评审；严格模式不能绕过 commit-reveal
        outsider = next(d for d in w.by_did if d not in js and d != c.author)
        a = attestation.create_attestation(
            w.by_did[outsider],
            c.id,
            accuracy=1,
            quality=1,
            usefulness=1,
            stake=5,
            created_at=w.t,
            round=0,
        )
        with self.assertRaises(NodeError):
            w.node.commit(attestation.create_commit(w.by_did[outsider], a, "s"), w.t)
        with self.assertRaises(NodeError):
            w.node.attest(a, w.t)
        # 抽签是加权无放回的
        self.assertEqual(len(set(jury.draw({"a": 1, "b": 2, "c": 3}, 2, "seed"))), 2)

    def test_new_accounts_not_jurors(self):
        """REQ-CS-002 REQ-PS-009"""
        w = World(n_jurors=3)
        newbie = w.add("newbie")
        w.record("alice", "invite", {"invitee": newbie.did})
        w.node.register(newbie.did, w.t)
        c = w.publish("bob", body(2))
        w.tick()
        self.assertNotIn(newbie.did, w.node.jurors(c.id))

    def test_commit_reveal(self):
        """REQ-CS-005"""
        w = World()
        c = w.publish("alice", body(3))
        w.tick()
        r = w.node.state[c.id].open_round
        did = r.jurors[0]
        a = attestation.create_attestation(
            w.by_did[did],
            c.id,
            accuracy=0.8,
            quality=0.8,
            usefulness=0.8,
            stake=10,
            created_at=w.t,
            round=0,
        )
        cm = attestation.create_commit(w.by_did[did], a, "salt")
        self.assertNotIn("0.8", str(cm.to_dict()))  # 承诺不泄露分数
        w.node.commit(cm, r.opened_at + 1)
        with self.assertRaises(NodeError):  # 揭示期未到
            w.node.reveal(a, "salt", r.opened_at + 2)
        with self.assertRaises(NodeError):  # 盐不对
            w.node.reveal(a, "wrong", r.opened_at + w.config.commit_window_s + 1)
        other = attestation.create_attestation(
            w.by_did[did],
            c.id,
            accuracy=0.1,
            quality=0.1,
            usefulness=0.1,
            stake=10,
            created_at=w.t,
            round=0,
        )
        with self.assertRaises(NodeError):  # 不能改分
            w.node.reveal(other, "salt", r.opened_at + w.config.commit_window_s + 1)
        w.node.reveal(a, "salt", r.opened_at + w.config.commit_window_s + 1)
        with self.assertRaises(NodeError):  # 承诺期已过
            j2 = r.jurors[1]
            a2 = attestation.create_attestation(
                w.by_did[j2],
                c.id,
                accuracy=0.8,
                quality=0.8,
                usefulness=0.8,
                stake=10,
                created_at=w.t,
                round=0,
            )
            w.node.commit(
                attestation.create_commit(w.by_did[j2], a2, "x"),
                r.opened_at + w.config.commit_window_s,
            )

    def test_discovery_reward_weights(self):
        """REQ-CS-005"""
        w = World()
        c = w.publish("alice", body(4))
        w.run_round(c.id, 0.9)
        r1 = w.run_round(c.id, 0.9)
        cur = w.node.curators_for(c.id)
        first = w.node.state[c.id].rounds[0].jurors
        self.assertEqual({cur[d] for d in first}, {30})  # 首轮 ×3
        self.assertEqual({cur[d] for d in r1.jurors}, {20})  # 第二轮 ×2
        self.assertEqual(jury.wave_weight(5), 1)


class TestWaves(unittest.TestCase):
    def test_waves_promote_step_by_step(self):
        """REQ-CS-003 REQ-AT-005"""
        w = World(n_jurors=20)
        c = w.publish("alice", body(5))
        levels = []
        for _ in range(4):
            w.run_round(c.id, 0.9)
            levels.append(w.node.state[c.id].level)
        self.assertEqual(levels, [1, 2, 3, 4])  # 每轮只晋一级
        caps = w.config.wave_caps
        self.assertTrue(all(b / a <= 10 for a, b in itertools.pairwise(caps)))
        # 不达标不晋级
        d = w.publish("bob", body(6))
        w.run_round(d.id, 0.5)
        self.assertEqual(w.node.state[d.id].level, 0)

    def test_exposure_cap_enforced(self):
        """REQ-CS-003"""
        n = SignalNode("n", explore_ratio=0.0)
        n.config.wave_caps = (2, 20)
        c = make_content()
        n.publish(c)
        n.attest(make_att("r1", c.id, 0.5))
        n.settle(c.id)  # 0.5 不晋级 → L0 上限 2 次
        shown = sum(1 for _ in range(5) if any(f.content_id == c.id for f in n.feed(T0)))
        self.assertEqual(shown, 2)

    def test_timed_settlement(self):
        """REQ-AT-005"""
        w = World()
        c = w.publish("alice", body(7))
        w.tick()
        r = w.node.state[c.id].open_round
        w.node.tick(r.opened_at + w.config.round_window_s - 1)
        self.assertFalse(r.settled or r.failed)
        w.node.tick(r.opened_at + w.config.round_window_s)
        self.assertTrue(r.failed)  # 无人揭示 → 本轮失败（进入二次机会）

    def test_second_chance(self):
        """REQ-EV-005"""
        w = World()
        c = w.publish("alice", body(8))
        w.tick()
        for _ in range(3):
            r = w.node.state[c.id].open_round
            self.assertIsNotNone(r)
            w.node.tick(r.opened_at + w.config.round_window_s)
        st = w.node.state[c.id]
        self.assertEqual(st.chances, 2)
        self.assertEqual([x.kind for x in st.rounds], ["wave", "second_chance", "second_chance"])
        self.assertEqual(st.status, "insufficient")  # 第 3 次不再进入
        self.assertFalse(w.node.explore_eligible(c.id))
        jurors = [set(x.jurors) for x in st.rounds]
        self.assertFalse(jurors[0] & jurors[1])  # 每次都是新陪审

    def test_rereview_classic_and_outdated(self):
        """REQ-EV-004"""
        w = World(n_jurors=20)
        keep = w.publish("alice", body(9))
        drop = w.publish("bob", body(10))
        w.run_round(keep.id, 0.9)
        w.run_round(drop.id, 0.9)
        first = w.node.state[keep.id].first_settled_at
        w.t = first + 30 * DAY
        w.node.tick(w.t)  # 开复审轮
        self.assertEqual(w.node.state[keep.id].open_round.kind, "rereview")
        w.run_round(keep.id, 0.88)
        w.run_round(drop.id, 0.4)
        self.assertTrue(w.node.state[keep.id].classic)
        self.assertTrue(w.node.state[drop.id].outdated)
        self.assertLess(w.node.state[drop.id].level, w.node.state[keep.id].level)


class TestPublishStake(unittest.TestCase):
    def test_stake_and_quota(self):
        """REQ-CS-006"""
        w = World()
        a = w.ids["alice"].did
        cs = [w.publish("alice", body(20 + i), title=f"t{i}") for i in range(4)]
        self.assertEqual(w.node.rep.locked(a), 5 * 4)
        self.assertEqual([w.node.explore_eligible(c.id) for c in cs], [True, True, True, False])
        before = w.node.rep.balance(w.ids["bob"].did)
        spam = w.publish("bob", body(30))
        w.run_round(spam.id, 0.1)
        self.assertLessEqual(w.node.rep.balance(w.ids["bob"].did), before - 5)
        self.assertEqual(w.node.rep.locked(w.ids["bob"].did), 0)


class TestReaderSignals(unittest.TestCase):
    def test_divergence_triggers_review(self):
        """REQ-CS-007"""
        w = World(n_jurors=20)
        c = w.publish("alice", body(40))
        for i in range(6):
            reader = w.add(f"reader{i}")
            w.record(f"j{i}", "invite", {"invitee": reader.did})  # 生产模式读者也需邀请注册
            w.node.submit(
                records.sign_record(
                    reader,
                    "reader_signal",
                    {"content_id": c.id, "completed": False, "saved": False, "worth": 0.1},
                ),
                w.t,
            )
        self.assertLess(w.node.reader_score(c.id), 0.2)
        with self.assertRaises(NodeError):  # 每位读者只能发一次
            w.node.submit(
                records.sign_record(
                    w.ids["reader0"],
                    "reader_signal",
                    {"content_id": c.id, "completed": True, "saved": True, "worth": 1.0},
                ),
                w.t,
            )
        w.run_round(c.id, 0.9)  # 陪审 0.9 vs 读者 ~0.07：背离
        st = w.node.state[c.id]
        self.assertEqual(st.level, 0)  # 不晋级
        self.assertEqual(st.open_round.kind, "review")  # 进入复审


class TestBridging(unittest.TestCase):
    def test_single_group_penalized(self):
        """REQ-PS-008"""
        n = SignalNode("n")
        for _g, members in (("x", ["a1", "a2", "a3"]), ("y", ["b1", "b2", "b3"])):
            for m in members:
                for o in members:
                    if m != o:
                        n.submit(
                            records.sign_record(ident(m), "follow", {"followee": ident(o).did})
                        )
        cl = n.clusters()
        self.assertEqual(cl[ident("a1").did], cl[ident("a3").did])
        self.assertNotEqual(cl[ident("a1").did], cl[ident("b1").did])
        both = make_content(author="p", title="跨群体")
        one = make_content(author="q", title="单群体")
        n.publish(both)
        n.publish(one)
        for r in ("a1", "a2", "b1", "b2"):
            n.attest(make_att(r, both.id, 0.8))
        for r in ("a1", "a2", "a3"):
            n.attest(make_att(r, one.id, 0.8))
        s_both, s_one = n.settle(both.id), n.settle(one.id)
        self.assertTrue(s_both.bridged)
        self.assertFalse(s_one.bridged)
        self.assertLess(s_one.confidence, s_both.confidence)


class TestCategoryWeights(unittest.TestCase):
    def test_category_specific_weights(self):
        """REQ-PS-011"""
        a = attestation.create_attestation(
            ident("r"),
            "cid",
            accuracy=1.0,
            quality=0.0,
            usefulness=0.0,
            originality=0.0,
            stake=5,
            created_at=T0,
        )
        self.assertAlmostEqual(a.score_with(attestation.CATEGORY_WEIGHTS["news"]), 0.45)
        self.assertAlmostEqual(a.score_with(attestation.CATEGORY_WEIGHTS["art"]), 0.05)
        for wts in attestation.CATEGORY_WEIGHTS.values():
            self.assertAlmostEqual(sum(wts.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
