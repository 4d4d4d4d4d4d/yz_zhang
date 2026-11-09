import dataclasses
import unittest

from signalnet import ads, attestation
from signalnet.federation import FederationError, NodeInfo, TrafficRouter
from signalnet.node import SignalNode
from tests.helpers import T0, ident, make_att, make_content


class TestFederation(unittest.TestCase):
    def test_hub_share_capped(self):
        """REQ-FD-001"""
        r = TrafficRouter(max_hub_share=0.2)
        r.add(NodeInfo("hub", "hub", capacity=100))
        for i in range(4):
            r.add(NodeInfo(f"p{i}", "peer"))
        for _ in range(1000):
            r.route()
        self.assertLessEqual(r.share("hub"), 0.2 + 1e-9)
        self.assertGreater(r.share("hub"), 0.15)  # 仍然发挥效率优势
        with self.assertRaises(FederationError):
            NodeInfo("x", "superhub")

    def test_replay_reproduces_state(self):
        """REQ-FD-002"""
        n = SignalNode("a")
        c = make_content(tags=("ai",))
        n.publish(c)
        for r, s in (("r1", 0.8), ("r2", 0.7), ("r3", 0.1)):
            n.attest(make_att(r, c.id, s))
        n.settle_all()
        n.add_campaign(ads.Campaign("c1", "acme", 10**6, 10**5))
        n.view_ad(ident("v").did, "c1", c.id, 3000, T0)
        replica = SignalNode.replay(n.ledger, "b")
        self.assertEqual(replica.state_digest(), n.state_digest())
        # 篡改日志中的评审分数 → 签名失败，无法重放
        evs = list(n.ledger)
        i = next(k for k, e in enumerate(evs) if e.kind == "attest")
        tampered = {**evs[i].data["att"], "accuracy": 1.0}
        evs[i] = dataclasses.replace(evs[i], data={**evs[i].data, "att": tampered})
        with self.assertRaises(attestation.AttestationError):
            SignalNode.replay(evs, "c")


class TestCli(unittest.TestCase):
    def test_demo_end_to_end(self):
        from signalnet.cli import run_demo

        out = run_demo()
        self.assertTrue(out["ledger_ok"])
        self.assertTrue(out["replay_matches"])
        self.assertGreater(out["consensus"]["good"], out["consensus"]["spam"])
        self.assertTrue(all(r < 100 for r in out["shill_rep"]))
        self.assertEqual(len(out["feed"]), 1)  # REQ-RK-005：垃圾内容不进推荐流


if __name__ == "__main__":
    unittest.main()
