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


# ---------------- 生产模式夹具 ----------------
from signalnet import attestation as _att  # noqa: E402
from signalnet import records as _rec  # noqa: E402
from signalnet.node import NodeConfig, SignalNode  # noqa: E402

LONG = (
    "我们用三个月时间实测了五种 AI 视频生成工具的单条成本：模型费用平均只占总成本的百分之三，"
    "投流费用却占到百分之八十五。下面给出完整的数据表、统计方法和可复现的脚本。"
)


def body(i: int) -> str:
    """足够长且彼此不相似的正文（避免触发查重/母题）。"""
    words = [crypto.sha256_hex(f"{i}-{k}".encode())[:6] for k in range(12)]
    return "第" + str(i) + "篇：" + "，".join(words) + "。这是一段用于测试的独立正文内容。"


class World:
    """生产模式测试世界：若干创世陪审 + 一个节点。"""

    def __init__(self, n_jurors: int = 20, **cfg):
        self.ids = {f"j{i}": ident(f"j{i}") for i in range(n_jurors)}
        for name in ("alice", "bob", "carol"):
            self.ids[name] = ident(name)
        genesis = tuple(i.did for i in self.ids.values())
        cfg.setdefault("jury_size", 3)
        self.config = NodeConfig.production(genesis=genesis, **cfg)
        self.node = SignalNode("n", config=self.config)
        self.t = T0
        for i in self.ids.values():
            self.node.register(i.did, self.t)
        self.by_did = {i.did: i for i in self.ids.values()}

    def add(self, name: str) -> crypto.Identity:
        i = ident(name)
        self.ids[name] = i
        self.by_did[i.did] = i
        return i

    def publish(self, author: str, text: str, title: str = "标题", **kw):
        c = content.create_content(
            self.ids[author], title, text, created_at=self.t, ai_generated=False, **kw
        )
        self.node.publish(c, self.t)
        return c

    def tick(self, dt: int = 1):
        self.t += dt
        self.node.tick(self.t)

    def run_round(self, cid: str, score, klass: str = "", stake: int = 10, **kw):
        """开轮（如需要）→ 全体陪审 commit → reveal → 截止结算。score 可为 {did: 分} 或数值。"""
        n = self.node
        if n.state[cid].open_round is None:
            self.tick()
        r = n.state[cid].open_round
        assert r is not None, "没有开放的轮次"
        pending = []
        for did in r.jurors:
            sc = score[did] if isinstance(score, dict) else score
            a = _att.create_attestation(
                self.by_did[did],
                cid,
                accuracy=sc,
                quality=sc,
                usefulness=sc,
                stake=stake,
                created_at=self.t,
                round=r.index,
                klass=klass,
                **kw,
            )
            salt = did[-8:]
            n.commit(_att.create_commit(self.by_did[did], a, salt), r.opened_at + 1)
            pending.append((a, salt))
        for a, salt in pending:
            n.reveal(a, salt, r.opened_at + self.config.commit_window_s + 1)
        self.t = r.opened_at + self.config.round_window_s
        n.tick(self.t)
        return r

    def record(self, who: str, kind: str, body: dict):
        return self.node.submit(_rec.sign_record(self.ids[who], kind, body), self.t)
