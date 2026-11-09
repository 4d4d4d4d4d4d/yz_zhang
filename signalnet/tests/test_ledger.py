import dataclasses
import unittest

from signalnet.ledger import Ledger


class TestLedger(unittest.TestCase):
    def test_hash_chain_detects_tamper(self):
        """REQ-LG-001"""
        lg = Ledger()
        for i in range(5):
            lg.append("x", {"i": i})
        self.assertTrue(lg.verify_chain())
        lg._events[2] = dataclasses.replace(lg._events[2], data={"i": 99})
        self.assertFalse(lg.verify_chain())

    def test_event_data_is_frozen_copy(self):
        """REQ-LG-002"""
        lg = Ledger()
        d = {"k": [1]}
        lg.append("x", d)
        d["k"].append(2)
        self.assertEqual(next(iter(lg)).data, {"k": [1]})
        self.assertTrue(lg.verify_chain())

    def test_of_kind(self):
        lg = Ledger()
        lg.append("a", {})
        lg.append("b", {})
        self.assertEqual(len(lg.of_kind("a")), 1)


if __name__ == "__main__":
    unittest.main()
