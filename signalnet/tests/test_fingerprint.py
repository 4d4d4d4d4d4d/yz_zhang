import unittest

from signalnet import content, fingerprint
from signalnet.node import SignalNode
from tests.helpers import T0, ident

A = (
    "用脚开瓶盖的技巧其实很简单：先把瓶子放在地面上固定好，然后用脚后跟对准瓶盖边缘，"
    "快速向上踢出。关键在于发力的角度要保持四十五度，力量集中在脚跟。"
)
NEAR = {
    "改几个字": A.replace("其实很简单", "非常简单").replace("快速", "迅速"),
    "加标点空格": "  " + A.replace("，", " , ") + "！！！",
    "调换两句": (
        "然后用脚后跟对准瓶盖边缘，快速向上踢出。先把瓶子放在地面上固定好，"
        "用脚开瓶盖的技巧其实很简单：关键在于发力的角度要保持四十五度，力量集中在脚跟。"
    ),
    "加一段开头": "大家好，今天教大家一个绝活。" + A,
}
DIFFERENT = (
    "今天测试了三种开瓶盖的方法：用打火机、用筷子和用牙齿。"
    "结果发现打火机最省力，牙齿最危险，不推荐大家尝试。"
)


def post(author, body, title="开瓶盖", created_at=T0):
    return content.create_content(
        ident(author), title, body, created_at=created_at, ai_generated=False
    )


class TestFingerprint(unittest.TestCase):
    def test_near_duplicates_detected(self):
        """REQ-OR-001"""
        for name, text in NEAR.items():
            d = fingerprint.distance(fingerprint.simhash(A), fingerprint.simhash(text))
            self.assertLessEqual(d, fingerprint.NEAR_DUP_BITS, name)
        far = fingerprint.distance(fingerprint.simhash(A), fingerprint.simhash(DIFFERENT))
        self.assertGreater(far, fingerprint.NEAR_DUP_BITS)
        self.assertFalse(fingerprint.long_enough("太短了"))

    def test_node_flags_copy_and_notifies_original(self):
        """REQ-OR-001"""
        n = SignalNode("n")
        orig = post("alice", A)
        n.publish(orig)
        copy = post("thief", NEAR["改几个字"], title="绝活")
        other = post("carol", DIFFERENT)
        own_repost = post("alice", NEAR["加一段开头"], title="再发一次")
        for c in (copy, other, own_repost):
            n.publish(c)
        self.assertEqual(n.near_duplicate_of(copy.id), orig.id)
        self.assertFalse(n.explore_eligible(copy.id))
        self.assertTrue(n.explore_eligible(orig.id))
        self.assertTrue(n.explore_eligible(other.id))
        self.assertIsNone(n.near_duplicate_of(own_repost.id))  # 同作者不算搬运
        self.assertEqual(
            n.notifications[orig.author],
            [{"kind": "near_duplicate", "copy": copy.id, "original": orig.id}],
        )
        # 判定结果可由日志重放复算
        self.assertEqual(SignalNode.replay(n.ledger, "b").state_digest(), n.state_digest())

    def test_ledger_order_beats_backdated_timestamp(self):
        """REQ-OR-001"""
        n = SignalNode("n")
        orig = post("alice", A, created_at=T0)
        n.publish(orig)
        backdated = post("thief", NEAR["调换两句"], title="我才是原创", created_at=T0 - 86400)
        n.publish(backdated)
        self.assertEqual(n.near_duplicate_of(backdated.id), orig.id)
        self.assertIsNone(n.near_duplicate_of(orig.id))


if __name__ == "__main__":
    unittest.main()
