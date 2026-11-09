import unittest
from dataclasses import replace

from signalnet import attestation, content, mesh, records, semantic, sim
from signalnet.node import NodeConfig, NodeError, SignalNode
from tests.helpers import T0, World, body, ident, make_att, make_content

DAY = 86_400

# 同一个挑战，各自改写的文案（没有共同标签）
REWRITES = [
    "用脚开瓶盖挑战：把啤酒瓶放在桌边，抬脚用脚后跟对准瓶盖边缘向上一踢，瓶盖就飞了。练了三天终于成功。",
    "今天终于学会了用脚开瓶盖！瓶子要放稳，脚后跟找准瓶盖的边，往上踢就行，失败了二十多次。",
    "挑战用脚踢开汽水瓶盖，关键是瓶子固定住，脚跟发力向上，第一次就成功了哈哈。",
    "跟风试了下脚开瓶盖，可乐瓶太滑了，踢了好多次瓶盖才掉，脚后跟都踢红了。",
    "脚踢瓶盖挑战来了，我用的是矿泉水瓶，把瓶子夹在桌角，用脚跟一踢盖子就开了。",
    "脚开瓶盖我练了一周，诀窍是瓶身别晃，脚后跟擦着瓶盖边缘往上带，瓶盖直接飞出去。",
]
UNRELATED = [
    "这是一篇关于量化交易中均值回归策略的回测报告，数据覆盖二零一五年至二零二五年的沪深三百成分股。",
    "今天做了番茄炒蛋，先把鸡蛋打散炒到半熟盛出，再炒番茄出汁，最后混合加盐和少许糖。",
    "周末去爬了香山，红叶还没完全变色，人非常多，建议工作日早上去，从东门上北门下比较轻松。",
    "新手学吉他最难的是F和弦，按不响通常是食指没有压平，可以先练习小横按再过渡到大横按。",
]


class TestSemantic(unittest.TestCase):
    def test_rewrites_vs_unrelated(self):
        """REQ-OR-010"""
        e = [semantic.embed(t) for t in REWRITES]
        u = [semantic.embed(t) for t in UNRELATED]
        same = [semantic.cosine(e[i], e[j]) for i in range(len(e)) for j in range(i + 1, len(e))]
        diff = [semantic.cosine(a, b) for a in e for b in u]
        self.assertGreater(min(same), max(diff))
        self.assertGreaterEqual(min(same), semantic.SIMILAR)
        self.assertLess(max(diff), semantic.SIMILAR)
        self.assertEqual(semantic.embed(REWRITES[0]), semantic.embed(REWRITES[0]))  # 确定性
        with self.assertRaises(ValueError):
            semantic.register_model(semantic.BASELINE, semantic.embed_baseline)

    def test_untagged_rewrites_form_motif(self):
        """REQ-OR-010"""
        n = SignalNode("n")
        cs = []
        for i, text in enumerate(REWRITES[:5]):
            c = content.create_content(
                ident(f"fan{i}"), f"挑战{i}", text, created_at=T0 + i * 3600, ai_generated=False
            )
            n.publish(c, T0 + i * 3600)
            cs.append(c)
        self.assertEqual(n.motif_of(cs[-1].id), cs[0].id)
        self.assertEqual(n.state[cs[3].id].prior_class, "follower")
        cand = n.similar_candidates(cs[-1].id)
        self.assertTrue(cand and cand[0][1] >= semantic.SIMILAR)
        self.assertEqual(n.similar_candidates(cs[0].id), [])  # 首发没有更早的相似内容

    def test_established_topic_not_motif(self):
        """REQ-OR-010"""
        n = SignalNode("n")
        old = content.create_content(
            ident("veteran"), "老话题", REWRITES[5], created_at=T0 - 60 * DAY, ai_generated=False
        )
        n.publish(old, T0 - 60 * DAY)
        for i, text in enumerate(REWRITES[:5]):
            c = content.create_content(
                ident(f"fan{i}"), f"挑战{i}", text, created_at=T0 + i, ai_generated=False
            )
            n.publish(c, T0 + i)
        self.assertEqual(n.motifs.motifs, {})  # 窗口之前已有同话题：常态话题


class TestJuryDuty(unittest.TestCase):
    def test_no_reveal_and_absence(self):
        """REQ-CS-008"""
        w = World()
        c = w.publish("alice", body(1))
        w.tick()
        r = w.node.state[c.id].open_round
        committer, absentee = r.jurors[0], r.jurors[1]
        a = attestation.create_attestation(
            w.by_did[committer],
            c.id,
            accuracy=0.8,
            quality=0.8,
            usefulness=0.8,
            stake=10,
            created_at=w.t,
            round=0,
        )
        w.node.commit(attestation.create_commit(w.by_did[committer], a, "s"), r.opened_at + 1)
        before = w.node.rep.balance(committer)
        pool_before = w.node._juror_pool(set())[absentee]
        w.node.tick(r.opened_at + w.config.round_window_s)
        self.assertEqual(w.node.rep.balance(committer), before - w.config.no_reveal_slash)
        self.assertEqual(w.node.absent[absentee], 1)
        self.assertAlmostEqual(w.node._juror_pool(set())[absentee], pool_before / 2)
        self.assertNotIn(committer, w.node.absent)


class TestGoldSet(unittest.TestCase):
    def test_audit_rewards_and_slashes(self):
        """REQ-CS-009"""
        w = World(n_jurors=20)
        c = w.publish("alice", body(2))
        w.run_round(c.id, 0.8)
        s_before = w.node.settlements[c.id]
        level_before = w.node.state[c.id].level
        with self.assertRaises(NodeError):
            w.node.add_gold("不存在", w.t)
        expected = w.node.add_gold(c.id, w.t)
        self.assertEqual(expected, 0.8)
        # 抽检轮在下一次 tick 开启（晋级后的波次轮先开，所以推进到其结束后）
        while w.node.state[c.id].open_round is None or (
            w.node.state[c.id].open_round.kind != "audit"
        ):
            r = w.node.state[c.id].open_round
            if r is None:
                w.tick()
                continue
            w.node.tick(r.opened_at + w.config.round_window_s)
        r = w.node.state[c.id].open_round
        good, bad = r.jurors[0], r.jurors[1]
        rep0 = {d: w.node.rep.balance(d) for d in (good, bad)}
        pending = []
        for did, sc in ((good, 0.82), (bad, 0.1)):
            a = attestation.create_attestation(
                w.by_did[did],
                c.id,
                accuracy=sc,
                quality=sc,
                usefulness=sc,
                stake=10,
                created_at=w.t,
                round=r.index,
            )
            w.node.commit(attestation.create_commit(w.by_did[did], a, "s"), r.opened_at + 1)
            pending.append(a)
        for a in pending:
            w.node.reveal(a, "s", r.opened_at + w.config.commit_window_s + 1)
        w.node.tick(r.opened_at + w.config.round_window_s)
        self.assertEqual(w.node.rep.balance(good), rep0[good] + w.config.audit_reward)
        self.assertEqual(w.node.rep.balance(bad), rep0[bad] - w.config.audit_slash)
        self.assertEqual(w.node.audit_misses[bad], 1)
        # 抽检轮不改变内容共识与级别
        self.assertEqual(w.node.settlements[c.id].consensus, s_before.consensus)
        self.assertEqual(w.node.state[c.id].level, level_before)
        self.assertEqual(
            SignalNode.replay(w.node.ledger, "b", config=w.config).state_digest(),
            w.node.state_digest(),
        )


class TestFeedSideEffects(unittest.TestCase):
    def test_build_is_pure_and_record_separate(self):
        """REQ-NW-004"""
        n = SignalNode("n")
        for i in range(4):
            c = make_content(author=f"a{i}", title=f"t{i}")
            n.publish(c)
            if i < 2:
                n.attest(make_att(f"r{i}", c.id, 0.8))
                n.settle(c.id)
        f1 = n.build_feed(T0)
        f2 = n.build_feed(T0)
        self.assertEqual(f1, f2)
        self.assertEqual(n.impressions, {})
        self.assertEqual(n.explore_impressions, {})
        n.record_impressions(f1)
        self.assertEqual(sum(n.impressions.values()), len([f for f in f1 if f.kind != "ad"]))
        self.assertTrue(n.explore_impressions)
        info = n.current_round(next(iter(n.state)))
        self.assertIsNone(info)  # 已结算的内容没有开放轮
        open_cid = next(cid for cid, st in n.state.items() if st.open_round)
        self.assertEqual(n.current_round(open_cid)["index"], 0)


def _mesh_world():
    ids = {n: ident(n) for n in ["alice", "thief", *[f"j{i}" for i in range(8)]]}
    genesis = tuple(i.did for i in ids.values())

    def factory():
        return NodeConfig.production(genesis=genesis, jury_size=3, min_reveals=1)

    return ids, factory


class TestMesh(unittest.TestCase):
    def test_multi_writer_converges(self):
        """REQ-FD-005"""
        ids, factory = _mesh_world()
        a = mesh.MeshNode("A", config_factory=factory)
        b = mesh.MeshNode("B", config_factory=factory)
        c1 = content.create_content(
            ids["alice"], "A 收到的", body(10), created_at=T0 + 10, ai_generated=False
        )
        c2 = content.create_content(
            ids["j0"], "B 收到的", body(11), created_at=T0 + 20, ai_generated=False
        )
        a.receive(mesh.op_publish(c1, T0 + 10), T0 + 11)
        b.receive(mesh.op_publish(c2, T0 + 20), T0 + 21)
        f = mesh.op_record(
            records.sign_record(ids["j1"], "follow", {"followee": ids["alice"].did}), T0 + 30
        )
        b.receive(f, T0 + 31)
        until = T0 + 3 * 3600
        self.assertNotEqual(a.state(until).state_digest(), b.state(until).state_digest())
        self.assertEqual(a.gossip(b), 3)
        self.assertEqual(a.set_digest(), b.set_digest())
        sa, sb = a.state(until), b.state(until)
        self.assertEqual(sa.state_digest(), sb.state_digest())
        self.assertEqual(sa.ledger.head, sb.ledger.head)
        self.assertIn(c1.id, sa.contents)
        self.assertIn(c2.id, sa.contents)
        self.assertEqual(a.gossip(b), 0)  # 幂等
        with self.assertRaises(mesh.MeshError):  # 伪造签名的操作在接收时即被拒
            bad = mesh.Op("publish", {**c1.to_dict(), "body": "篡改"}, T0)
            a.receive(bad, T0)

    def test_late_backdated_op_cannot_steal_originality(self):
        """REQ-FD-005"""
        ids, factory = _mesh_world()
        nodes = [mesh.MeshNode(n, config_factory=factory, epoch_s=3600, grace_s=600) for n in "ABC"]
        orig = content.create_content(
            ids["alice"], "原作", body(20), created_at=T0 + 100, ai_generated=False
        )
        for nd in nodes:
            nd.receive(mesh.op_publish(orig, T0 + 100), T0 + 120)
        # 搬运者倒填时间到原作之前，但 3 小时后才出现在网络里
        copy = content.create_content(
            ids["thief"], "我先发的", body(20), created_at=T0 + 1, ai_generated=False
        )
        late = mesh.op_publish(copy, T0 + 1)
        for nd in nodes:
            nd.receive(late, T0 + 3 * 3600)
        self.assertEqual(nodes[0].effective_epoch(late.id), (T0 + 3 * 3600) // 3600)
        st = nodes[0].state(T0 + 5 * 3600)
        self.assertEqual(st.near_duplicate_of(copy.id), orig.id)
        # 单个作恶节点谎称“按时收到”也无法把它提前（诚实见证占多数）
        evil = mesh.MeshNode("evil", config_factory=factory, epoch_s=3600, grace_s=600)
        evil.receive(late, T0 + 2)
        for nd in nodes:
            nd.gossip(evil)
        self.assertEqual(nodes[0].effective_epoch(late.id), (T0 + 3 * 3600) // 3600)
        st = nodes[0].state(T0 + 5 * 3600)
        self.assertEqual(st.near_duplicate_of(copy.id), orig.id)

    def test_jury_round_through_mesh(self):
        """REQ-FD-005"""
        ids, factory = _mesh_world()
        a, b = (
            mesh.MeshNode("A", config_factory=factory),
            mesh.MeshNode("B", config_factory=factory),
        )
        c = content.create_content(
            ids["alice"], "作品", body(30), created_at=T0, ai_generated=False
        )
        a.receive(mesh.op_publish(c, T0), T0)
        st = a.state(T0 + 2 * 3600)
        jurors = st.jurors(c.id)
        self.assertEqual(len(jurors), 3)
        by_did = {i.did: i for i in ids.values()}
        r = st.current_round(c.id)
        for k, did in enumerate(jurors):
            att = attestation.create_attestation(
                by_did[did],
                c.id,
                accuracy=0.9,
                quality=0.9,
                usefulness=0.9,
                stake=10,
                created_at=T0,
                round=r["index"],
            )
            node = a if k % 2 else b  # 陪审分别把操作交给不同节点
            node.receive(
                mesh.op_commit(
                    attestation.create_commit(by_did[did], att, "s"), r["opened_at"] + 10
                ),
                r["opened_at"] + 10,
            )
            node.receive(mesh.op_reveal(att, "s", r["commit_until"] + 10), r["commit_until"] + 10)
        a.gossip(b)
        until = r["closes_at"] + 3600
        sa, sb = a.state(until), b.state(until)
        self.assertEqual(sa.state[c.id].level, 1)
        self.assertEqual(sa.state_digest(), sb.state_digest())


class TestSimulation(unittest.TestCase):
    def test_reproducible(self):
        """REQ-SM-001"""
        cfg = replace(
            sim.SimConfig(),
            days=3,
            creators=10,
            honest_reviewers=15,
            readers=10,
            spammers=2,
            copycats=1,
            trend_followers=3,
        )
        self.assertEqual(sim.run(cfg), sim.run(cfg))
        other = sim.run(replace(cfg, seed=cfg.seed + 1))
        self.assertNotEqual(other, sim.run(cfg))

    def test_default_meets_thresholds(self):
        """REQ-SM-002"""
        m = sim.run()
        failed = [k for k, ok in m["passes"].items() if not ok]
        self.assertEqual(failed, [], m)
        self.assertTrue(m["reconciles"])
        self.assertEqual(m["spam_max_level"], 0)
        self.assertEqual(m["followers_in_motif"], m["followers"])

    def test_calibration_report_exists(self):
        """REQ-SM-003"""
        from pathlib import Path

        report = Path(__file__).resolve().parent.parent / "docs" / "reports" / "calibration.md"
        self.assertTrue(report.exists(), "运行 python3 harness/calibrate.py 生成校准报告")
        text = report.read_text(encoding="utf-8")
        self.assertIn("pass_rate", text)


if __name__ == "__main__":
    unittest.main()
