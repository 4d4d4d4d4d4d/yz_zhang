import dataclasses
import unittest

from signalnet import content, crypto
from tests.helpers import T0, ident, make_content


class TestIdentity(unittest.TestCase):
    def test_did_is_self_certifying(self):
        """REQ-ID-001"""
        i = ident("alice")
        self.assertTrue(i.did.startswith("did:sn:"))
        self.assertTrue(crypto.is_valid_did(i.did))
        self.assertEqual(i.did, ident("alice").did)
        self.assertNotEqual(i.did, ident("bob").did)
        self.assertFalse(crypto.is_valid_did("did:sn:zz"))

    def test_sign_verify_and_tamper(self):
        """REQ-ID-002"""
        i = ident("alice")
        sig = i.sign({"b": 1, "a": [1, 2]})
        self.assertTrue(crypto.verify(i.did, {"a": [1, 2], "b": 1}, sig))  # 键序无关
        self.assertFalse(crypto.verify(i.did, {"a": [1, 2], "b": 2}, sig))
        self.assertFalse(crypto.verify(ident("bob").did, {"a": [1, 2], "b": 1}, sig))
        self.assertFalse(crypto.verify(i.did, {}, "nothex"))


class TestContent(unittest.TestCase):
    def test_content_addressed(self):
        """REQ-CT-001"""
        a = make_content()
        b = make_content()
        self.assertEqual(a.id, b.id)
        self.assertNotEqual(a.id, make_content(title="另一个").id)
        self.assertEqual(content.Content.from_dict(a.to_dict()).id, a.id)

    def test_signature_required(self):
        """REQ-CT-002"""
        c = make_content()
        forged = dataclasses.replace(c, body="篡改")
        with self.assertRaises(content.ContentError):
            content.validate(forged)
        impostor = dataclasses.replace(c, author=ident("mallory").did)
        with self.assertRaises(content.ContentError):
            content.validate(impostor)

    def test_ai_disclosure_mandatory(self):
        """REQ-CT-003"""
        c = make_content(ai_generated=True)
        self.assertTrue(c.payload()["ai_generated"])
        with self.assertRaises(TypeError):
            content.create_content(ident("a"), "t", "b", created_at=T0)  # 不声明则无法创建
        bad = dataclasses.replace(c, ai_generated="yes")  # type: ignore[arg-type]
        with self.assertRaises(content.ContentError):
            content.validate(bad)

    def test_limits(self):
        with self.assertRaises(content.ContentError):
            make_content(title=" ")
        with self.assertRaises(content.ContentError):
            make_content(tags=tuple(str(i) for i in range(11)))


if __name__ == "__main__":
    unittest.main()
