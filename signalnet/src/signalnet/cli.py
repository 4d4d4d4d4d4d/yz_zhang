"""命令行入口：`python -m signalnet demo` 运行一个端到端仿真。"""

from __future__ import annotations

import argparse
import json

from . import ads, attestation, content, crypto, records
from .node import NodeConfig, SignalNode

T0 = 1_760_000_000


def run_demo() -> dict[str, object]:
    node = SignalNode("node-a")
    creators = {n: crypto.Identity.from_seed(n.encode()) for n in ("alice", "bob")}
    honest = [crypto.Identity.from_seed(f"rev{i}".encode()) for i in range(5)]
    shills = [crypto.Identity.from_seed(f"shill{i}".encode()) for i in range(2)]

    good = content.create_content(
        creators["alice"],
        "AI 视频降本实测",
        "完整数据与方法……",
        created_at=T0,
        ai_generated=True,
        tags=("ai", "video"),
    )
    spam = content.create_content(
        creators["bob"],
        "震惊！三天涨粉百万",
        "标题党……",
        created_at=T0,
        ai_generated=True,
        tags=("ai",),
    )
    for c in (good, spam):
        node.publish(c)
    for r in honest:
        node.attest(
            attestation.create_attestation(
                r, good.id, accuracy=0.9, quality=0.85, usefulness=0.8, stake=10, created_at=T0 + 60
            )
        )
        node.attest(
            attestation.create_attestation(
                r, spam.id, accuracy=0.2, quality=0.2, usefulness=0.1, stake=10, created_at=T0 + 60
            )
        )
    for s in shills:  # 合谋刷分者给垃圾内容打高分
        node.attest(
            attestation.create_attestation(
                s, spam.id, accuracy=1, quality=1, usefulness=1, stake=20, created_at=T0 + 60
            )
        )
    node.settle_all()
    node.add_campaign(ads.Campaign("camp-1", "acme", 1_000_000, 50_000, ("ai",)))
    for i in range(20):
        viewer = crypto.Identity.from_seed(f"viewer{i}".encode()).did
        node.view_ad(viewer, "camp-1", good.id, dwell_ms=3000, ts=T0 + 3600)
    replica = SignalNode.replay(node.ledger, "node-b")
    return {
        "feed": [f.content_id[:12] for f in node.feed(T0 + 3600)],
        "consensus": {
            "good": node.settlements[good.id].consensus,
            "spam": node.settlements[spam.id].consensus,
        },
        "shill_rep": [node.rep.balance(s.did) for s in shills],
        "honest_rep": node.rep.balance(honest[0].did),
        "alice_earn_micros": node.exchange.earnings.get(creators["alice"].did, 0),
        "ad_charged_micros": node.exchange.total_charged(),
        "ledger_ok": node.ledger.verify_chain(),
        "replay_matches": replica.state_digest() == node.state_digest(),
    }


LONG_BODY = (
    "我们用三个月时间实测了五种 AI 视频生成工具的单条成本：模型费用平均只占总成本的百分之三，"
    "投流费用却占到百分之八十五。下面给出完整的数据表、统计方法和可复现的脚本。"
)
SPAM_BODY = "震惊！三天涨粉百万的秘密，只要照做就能月入十万，名额有限，赶紧私信领取完整教程资料包。"


def run_production_demo() -> dict[str, object]:
    """生产模式端到端：邀请注册 → 抽签陪审 commit-reveal → 定时结算 → 波次晋级 →
    搬运识别与罚没 → 签名回执广告 → 托管释放 → 跨节点重放一致。"""
    ids = {n: crypto.Identity.from_seed(n.encode()) for n in ["alice", "inviter"]}
    reviewers = [crypto.Identity.from_seed(f"juror{i}".encode()) for i in range(15)]
    genesis = tuple([ids["alice"].did, ids["inviter"].did] + [r.did for r in reviewers])
    node = SignalNode("node-a", config=NodeConfig.production(genesis=genesis))
    by_did = {r.did: r for r in [*reviewers, ids["alice"], ids["inviter"]]}
    for r in reviewers:
        node.register(r.did, T0)
    node.register(ids["alice"].did, T0)
    node.register(ids["inviter"].did, T0)
    # 邀请制注册：bob（灌水者）与 thief（搬运者）
    for name in ("bob", "thief"):
        ids[name] = crypto.Identity.from_seed(name.encode())
        node.submit(records.sign_record(ids["inviter"], "invite", {"invitee": ids[name].did}), T0)
    good = content.create_content(
        ids["alice"],
        "AI 视频降本实测",
        LONG_BODY,
        created_at=T0,
        ai_generated=True,
        tags=("ai", "video"),
        category="tutorial",
    )
    spam = content.create_content(
        ids["bob"], "震惊", SPAM_BODY, created_at=T0, ai_generated=True, tags=("ai",)
    )
    copy = content.create_content(
        ids["thief"],
        "我的独家实测",
        LONG_BODY.replace("三个月", "90 天"),
        created_at=T0 - 999,
        ai_generated=True,
        tags=("ai",),
    )
    for c in (good, spam, copy):
        node.publish(c, T0 + 10)
    node.tick(T0 + 60)  # 开轮抽签
    scores = {good.id: (0.88, "original"), spam.id: (0.15, "original"), copy.id: (0.5, "copy")}
    salts: dict[tuple[str, str], tuple[attestation.Attestation, str]] = {}
    for cid, (sc, klass) in scores.items():
        for did in node.jurors(cid):
            a = attestation.create_attestation(
                by_did[did],
                cid,
                accuracy=sc,
                quality=sc,
                usefulness=sc,
                originality=sc,
                klass=klass,
                stake=10,
                created_at=T0 + 3600,
                round=0,
            )
            salt = crypto.sha256_hex(f"{did}{cid}".encode())[:16]
            node.commit(attestation.create_commit(by_did[did], a, salt), T0 + 3600)
            salts[(cid, did)] = (a, salt)
    for (_cid, _did), (a, salt) in sorted(salts.items()):
        node.reveal(a, salt, T0 + 49 * 3600)
    node.tick(T0 + 73 * 3600)  # 截止：自动结算并晋级
    node.add_campaign(ads.Campaign("camp-1", "acme", 10_000_000, 50_000, ("ai",)))
    viewers = [crypto.Identity.from_seed(f"viewer{i}".encode()) for i in range(20)]
    for v in viewers:
        receipt = records.sign_record(
            v,
            "view_receipt",
            {
                "campaign_id": "camp-1",
                "content_id": good.id,
                "node_id": "node-a",
                "dwell_ms": 3000,
                "ts": T0 + 80 * 3600,
            },
        )
        node.view_receipt(receipt, T0 + 80 * 3600)
    escrow_before = node.exchange.escrowed(good.author)
    node.tick(T0 + 80 * 3600 + 8 * 86400)  # 托管期满
    replica = SignalNode.replay(
        node.ledger, "node-b", config=NodeConfig.production(genesis=genesis)
    )
    return {
        "levels": {"good": node.state[good.id].level, "spam": node.state[spam.id].level},
        "consensus": {
            "good": node.settlements[good.id].consensus,
            "spam": node.settlements[spam.id].consensus,
        },
        "copy_detected": node.near_duplicate_of(copy.id) == good.id,
        "copy_status": node.state[copy.id].status,
        "thief_rep": node.rep.balance(ids["thief"].did),
        "bob_rep": node.rep.balance(ids["bob"].did),
        "alice_escrow_before_release": escrow_before,
        "alice_earn_micros": node.exchange.earnings.get(good.author, 0),
        "reconciles": node.exchange.reconciles(),
        "ledger_ok": node.ledger.verify_chain(),
        "replay_matches": replica.state_digest() == node.state_digest()
        and replica.ledger.head == node.ledger.head,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="signalnet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    demo = sub.add_parser("demo", help="运行端到端仿真")
    demo.add_argument("--production", action="store_true", help="生产模式（陪审/回执/托管）")
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        out = run_production_demo() if args.production else run_demo()
        print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0
