"""命令行入口：`python -m signalnet demo` 运行一个端到端仿真。"""

from __future__ import annotations

import argparse
import json

from . import ads, attestation, content, crypto
from .node import SignalNode

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="signalnet")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo", help="运行端到端仿真")
    args = ap.parse_args(argv)
    if args.cmd == "demo":
        print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
    return 0
