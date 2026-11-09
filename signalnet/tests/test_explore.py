import unittest

from signalnet import content, reputation
from signalnet.node import SignalNode
from tests.helpers import T0, ident, make_att, make_content
from tests.test_fingerprint import NEAR, A


def explored(feed):
    return [f.content_id for f in feed if f.kind == "explore"]


class TestExplorePool(unittest.TestCase):
    def setUp(self):
        self.n = SignalNode("n", explore_ratio=0.1)
        # 12 条已结算的自然内容
        for i in range(12):
            c = make_content(author=f"old{i}", title=f"老内容{i}")
            self.n.publish(c)
            self.n.attest(make_att(f"r{i}", c.id, 0.8))
        self.n.settle_all()
        self.new = [make_content(author=f"new{i}", title=f"新作{i}") for i in range(5)]
        for c in self.new:
            self.n.publish(c)

    def test_new_content_gets_equal_exposure(self):
        """REQ-CS-001"""
        for k in range(10):
            feed = self.n.feed(T0, limit=10, viewer=f"v{k}")
            self.assertEqual(len(explored(feed)), 1)
            self.assertEqual(sum(1 for f in feed if f.kind != "ad"), 10)
            self.assertTrue(all(f.label == "新作探索" for f in feed if f.kind == "explore"))
        counts = [self.n.explore_impressions[c.id] for c in self.new]
        self.assertEqual(counts, [2] * 5)

    def test_independent_of_reputation(self):
        """REQ-CS-001"""
        n = SignalNode("n", pos_params=reputation.PoSParams(), explore_ratio=0.5)
        star, nobody = (
            make_content(author="star", title="大V"),
            make_content(author="nobody", title="新人"),
        )
        n.publish(star)
        n.publish(nobody)
        n.rep._balance[ident("star").did] = 100_000  # 声誉再高也不多拿探索曝光
        for k in range(6):
            n.feed(T0, limit=2, viewer=f"v{k}")
        self.assertEqual(n.explore_impressions[star.id], n.explore_impressions[nobody.id])

    def test_eligibility_and_ratio(self):
        """REQ-CS-001"""
        n = SignalNode("n", explore_ratio=0.1)
        orig = content.create_content(ident("alice"), "原作", A, created_at=T0, ai_generated=False)
        copy = content.create_content(
            ident("thief"), "搬运", NEAR["改几个字"], created_at=T0, ai_generated=False
        )
        n.publish(orig)
        n.publish(copy)
        settled = make_content(author="bob", title="已结算")
        n.publish(settled)
        n.attest(make_att("r", settled.id, 0.8))
        n.settle(settled.id)
        ids = explored(n.feed(T0, limit=10))
        self.assertIn(orig.id, ids)  # 自然内容不足时由探索内容补齐
        self.assertNotIn(copy.id, ids)
        self.assertNotIn(settled.id, ids)
        off = SignalNode("off", explore_ratio=0.0)
        off.publish(make_content(author="x", title="无探索"))
        self.assertEqual(explored(off.feed(T0)), [])


if __name__ == "__main__":
    unittest.main()
