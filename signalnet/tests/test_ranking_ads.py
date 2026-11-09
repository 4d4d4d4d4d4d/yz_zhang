import ast
import pathlib
import unittest

from signalnet import ads, ranking
from signalnet.node import SignalNode
from signalnet.ranking import RankInput, rank
from tests.helpers import T0, ident, make_att, make_content


def ri(cid, author="a", consensus=0.8, confidence=0.8, created_at=T0):
    return RankInput(cid, author, consensus, confidence, created_at)


class TestRanking(unittest.TestCase):
    def test_deterministic(self):
        """REQ-RK-001"""
        items = [ri("b"), ri("a", author="x"), ri("c", author="y")]
        self.assertEqual(rank(items, T0), rank(list(reversed(items)), T0))
        self.assertEqual(rank(items, T0)[:2], ["a", "b"])

    def test_ads_cannot_buy_ranking(self):
        """REQ-RK-002"""
        src = pathlib.Path(ranking.__file__).read_text(encoding="utf-8")
        imported = {
            (n.module or "") for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)
        } | {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(any("ads" in m for m in imported))
        fields = set(RankInput.__dataclass_fields__)
        self.assertFalse(fields & {"bid", "spend", "budget", "boost", "paid"})
        # 行为层面：投放巨额广告前后，自然排序完全一致
        n = SignalNode("n")
        a, b = make_content(author="a", title="A"), make_content(author="b", title="B")
        for c, s in ((a, 0.9), (b, 0.3)):
            n.publish(c)
            for r in ("r1", "r2", "r3"):
                n.attest(make_att(r + c.title, c.id, s))
        n.settle_all()
        before = [f.content_id for f in n.feed(T0) if f.kind == "organic"]
        n.add_campaign(ads.Campaign("big", "rich", 10**12, 10**9, ("x",)))
        after = [f.content_id for f in n.feed(T0) if f.kind == "organic"]
        self.assertEqual(before, after)
        self.assertEqual(before[0], a.id)

    def test_time_decay(self):
        """REQ-RK-003"""
        old, new = (
            ri("old", author="x", created_at=T0),
            ri("new", author="y", created_at=T0 + 3 * 86400),
        )
        self.assertEqual(rank([old, new], T0 + 3 * 86400), ["new", "old"])
        self.assertEqual(rank([ri("z", confidence=0.0)], T0), [])

    def test_author_diversity(self):
        """REQ-RK-004"""
        items = [ri("a1", "a", 0.9), ri("a2", "a", 0.9), ri("b1", "b", 0.6)]
        self.assertEqual(rank(items, T0), ["a1", "b1", "a2"])


class TestAds(unittest.TestCase):
    def setUp(self):
        self.n = SignalNode("node-a")
        self.c = make_content(tags=("ai",))
        self.n.publish(self.c)
        for r, s in (("r1", 0.8), ("r2", 0.8), ("r3", 0.8), ("bad", 0.0)):
            self.n.attest(make_att(r, self.c.id, s, stake=10))
        self.n.settle(self.c.id)
        self.n.add_campaign(ads.Campaign("c1", "acme", 1_000_000, 100_000, ("ai",)))

    def view(self, viewer="v1", dwell=3000, ts=T0):
        return self.n.view_ad(ident(viewer).did, "c1", self.c.id, dwell, ts)

    def test_creator_earns_from_views(self):
        """REQ-AD-001"""
        p = self.view()
        self.assertEqual(p.charged, 100)
        self.assertEqual(p.shares[self.c.author], 60)
        with self.assertRaises(ads.AdError):
            ads.RevenueSplit(creator_bps=4000, curators_bps=3000, node_bps=2000, commons_bps=1000)

    def test_valid_view_rules(self):
        """REQ-AD-002"""
        self.assertIsNone(self.view(dwell=500))
        self.assertIsNotNone(self.view())
        self.assertIsNone(self.view())  # 同日去重
        self.assertIsNotNone(self.view(ts=T0 + 86400))
        self.assertIsNone(self.n.view_ad(self.c.author, "c1", self.c.id, 3000, T0))  # 自刷
        ex = ads.AdExchange()
        ex.add_campaign(ads.Campaign("tiny", "x", 150, 100_000))
        v = ads.AdView("v", "tiny", "cid", "creator", "n", 3000, T0)
        self.assertIsNotNone(ex.record_view(v, {}))
        self.assertIsNone(
            ex.record_view(ads.AdView("w", "tiny", "cid", "creator", "n", 3000, T0), {})
        )

    def test_conservation(self):
        """REQ-AD-003"""
        for amount in (1, 7, 99, 100, 12345):
            shares = ads.split_revenue(
                amount, "c", "n", {"x": 3, "y": 7, "z": 1}, ads.RevenueSplit()
            )
            self.assertEqual(sum(shares.values()), amount)
        for i in range(30):
            self.view(viewer=f"v{i}")
        self.assertEqual(sum(self.n.exchange.earnings.values()), self.n.exchange.total_charged())

    def test_curators_are_aligned_reviewers(self):
        """REQ-AD-004"""
        p = self.view()
        self.assertIn(ident("r1").did, p.shares)
        self.assertNotIn(ident("bad").did, p.shares)
        no_cur = ads.split_revenue(100, "c", "n", {}, ads.RevenueSplit())
        self.assertEqual(no_cur[ads.COMMONS], 25)

    def test_ad_slots_labeled_and_capped(self):
        """REQ-AD-005"""
        with self.assertRaises(ads.AdError):
            ads.AdExchange(slot_interval=2)
        n = SignalNode("n", exchange=ads.AdExchange(slot_interval=3))
        n.add_campaign(ads.Campaign("c1", "acme", 10**6, 10**5))
        for i in range(6):
            c = make_content(author=f"a{i}", title=f"t{i}")
            n.publish(c)
            n.attest(make_att(f"r{i}", c.id, 0.8))
        n.settle_all()
        feed = n.feed(T0)
        ad_items = [f for f in feed if f.kind == "ad"]
        self.assertEqual(len(ad_items), 2)
        self.assertTrue(all(f.label == "广告" for f in ad_items))
        self.assertEqual([f.kind for f in feed[:4]], ["organic"] * 3 + ["ad"])


if __name__ == "__main__":
    unittest.main()
