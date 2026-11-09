import unittest

from signalnet import attestation, reputation
from signalnet.node import NodeError, SignalNode
from tests.helpers import ident, make_att, make_content


def node_with_content():
    n = SignalNode("n")
    c = make_content()
    n.publish(c)
    return n, c


class TestAttestation(unittest.TestCase):
    def test_scores_range_and_signature(self):
        """REQ-AT-001"""
        a = make_att("r1", "cid", 0.5)
        self.assertTrue(a.verify())
        self.assertAlmostEqual(a.score, 0.5)
        with self.assertRaises(attestation.AttestationError):
            make_att("r1", "cid", 1.5)

    def test_stake_positive_and_bounded(self):
        """REQ-AT-002"""
        with self.assertRaises(attestation.AttestationError):
            make_att("r1", "cid", 0.5, stake=0)
        n, c = node_with_content()
        with self.assertRaises(NodeError):  # 100 * 0.2 = 20 上限
            n.attest(make_att("r1", c.id, 0.5, stake=21))
        n.attest(make_att("r2", c.id, 0.5, stake=20))
        self.assertEqual(n.rep.locked(ident("r2").did), 20)

    def test_one_review_per_reviewer_and_window_closes(self):
        """REQ-AT-003"""
        n, c = node_with_content()
        n.attest(make_att("r1", c.id, 0.5))
        with self.assertRaises(NodeError):
            n.attest(make_att("r1", c.id, 0.6))
        n.settle(c.id)
        with self.assertRaises(NodeError):
            n.attest(make_att("r2", c.id, 0.6))

    def test_author_cannot_self_attest(self):
        """REQ-AT-004 REQ-PS-006"""
        n, c = node_with_content()
        with self.assertRaises(NodeError):
            n.attest(make_att("alice", c.id, 1.0))
        book = reputation.ReputationBook()
        with self.assertRaises(reputation.ReputationError):
            book.compute([make_att("alice", c.id, 1.0)], ident("alice").did)
        s = book.compute(
            [make_att("alice", c.id, 1.0), make_att("r1", c.id, 0.3)], ident("alice").did
        )
        self.assertAlmostEqual(s.consensus, 0.3)


class TestPoS(unittest.TestCase):
    def test_reputation_not_transferable(self):
        """REQ-PS-001"""
        public = {m for m in dir(reputation.ReputationBook) if not m.startswith("_")}
        for banned in ("transfer", "send", "mint", "sell", "buy"):
            self.assertFalse(any(banned in m for m in public), banned)

    def test_weighted_median_sqrt(self):
        """REQ-PS-002"""
        self.assertEqual(reputation.weighted_median([(0.1, 1), (0.9, 3)]), 0.9)
        self.assertEqual(reputation.capped_weights([4, 9], 0.34), [2.0, 3.0])

    def test_weight_cap(self):
        """REQ-PS-003"""
        w = reputation.capped_weights([10000, 1, 1, 1], 0.34)
        self.assertLessEqual(max(w) / sum(w), 0.34 + 1e-9)

    def test_reward_and_slash(self):
        """REQ-PS-004"""
        n, c = node_with_content()
        for r in ("r1", "r2", "r3"):
            n.attest(make_att(r, c.id, 0.8, stake=20))
        n.attest(make_att("liar", c.id, 0.0, stake=20))
        s = n.settle(c.id)
        self.assertEqual(n.rep.balance(ident("r1").did), 102)
        self.assertEqual(n.rep.balance(ident("liar").did), 96)
        self.assertEqual(n.rep.locked(ident("r1").did), 0)
        self.assertGreater(s.author_delta, 0)
        book = reputation.ReputationBook()
        book.register("x")
        book.apply(reputation.Settlement("c", 0.5, 0.5, slashes={"x": 10_000}), [])
        self.assertEqual(book.balance("x"), 0)  # 不为负

    def test_settlement_pure_and_no_double_settle(self):
        """REQ-PS-005"""
        n, c = node_with_content()
        n.attest(make_att("r1", c.id, 0.7))
        atts = n.attestations[c.id]
        before = n.rep.snapshot()
        s1 = n.rep.compute(atts, c.author)
        s2 = n.rep.compute(list(reversed(atts)), c.author)
        self.assertEqual(s1, s2)
        self.assertEqual(n.rep.snapshot(), before)
        n.settle(c.id)
        with self.assertRaises(NodeError):
            n.settle(c.id)

    def test_minority_collusion_fails(self):
        """REQ-PS-007"""
        n = SignalNode("n")
        spam = make_content(author="bob", title="spam")
        n.publish(spam)
        for i in range(5):
            n.attest(make_att(f"h{i}", spam.id, 0.1, stake=10))
        for i in range(3):  # 合谋者质押更多
            n.attest(make_att(f"s{i}", spam.id, 1.0, stake=20))
        s = n.settle(spam.id)
        self.assertLess(s.consensus, 0.3)
        self.assertTrue(all(n.rep.balance(ident(f"s{i}").did) < 100 for i in range(3)))


if __name__ == "__main__":
    unittest.main()
