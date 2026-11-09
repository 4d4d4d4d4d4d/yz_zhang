"""测试夹具：确定性身份与常用构造器。"""

from signalnet import attestation, content, crypto

T0 = 1_760_000_000


def ident(name: str) -> crypto.Identity:
    return crypto.Identity.from_seed(name.encode())


def make_content(author: str = "alice", title: str = "标题", created_at: int = T0, **kw):
    kw.setdefault("ai_generated", False)
    return content.create_content(ident(author), title, "正文", created_at=created_at, **kw)


def make_att(reviewer: str, cid: str, score: float, stake: int = 10):
    return attestation.create_attestation(
        ident(reviewer),
        cid,
        accuracy=score,
        quality=score,
        usefulness=score,
        stake=stake,
        created_at=T0 + 60,
    )
