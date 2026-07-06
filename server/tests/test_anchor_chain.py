"""SC-011 存证哈希链防篡改深度校验：不止「改内容被发现」，而是哈希链的核心保证——

任何对历史记录的修改都无法在不重写整条后继链的前提下蒙混过关。
现有测试只覆盖「裸改 payload」（payload_hash 对不上）这一条路径；
本套件补上更狡猾的攻击面：
  1. 连 payload_hash 一起改（骗过逐行哈希）→ 仍被 chain_hash 抓出；
  2. 把某行三重哈希全部自洽伪造 → 破坏下一行的 prev 链接（多米诺）；
  3. 删除中间记录 → 后继 prev 链接断裂；
  4. 创世链接：首条必须挂在 GENESIS 上。
"""
import hashlib

import sqlalchemy as sa

from app.core.db import engine

from .conftest import auth
from .test_task_flow import match_and_fund, publish_task
from .conftest import topup


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _build_chain(client, requester, worker):
    """跑一条完整闭环，产出 signed/funded/released 三条存证，返回 (contract_id)。"""
    topup(client, requester, 40000)
    task = publish_task(client, requester)
    contract_id = match_and_fund(client, requester, worker, task)
    client.post(f"/api/v1/tasks/{task['id']}/deliver", headers=auth(worker))
    client.post(f"/api/v1/tasks/{task['id']}/accept-delivery", headers=auth(requester))
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is True and v["total"] == 3
    return contract_id


def test_sophisticated_tamper_with_recomputed_payload_hash_still_caught(client, requester, worker):
    """狡猾攻击：改 payload 的同时把 payload_hash 一并改成自洽 —— 逐行哈希被骗过，
    但 chain_hash = sha(prev + payload_hash) 变了却没同步，链校验仍在该行失败。"""
    _build_chain(client, requester, worker)
    forged_payload = '{"amount_cents": 1}'
    forged_ph = _sha(forged_payload)
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE anchor_entries SET payload = :p, payload_hash = :h WHERE seq = 2"),
            {"p": forged_payload, "h": forged_ph},
        )
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is False and v["broken_at_seq"] == 2


def test_fully_self_consistent_row_forge_breaks_next_link(client, requester, worker):
    """把 seq=2 整行三重哈希全部改成自洽（payload/payload_hash/chain_hash 内部一致）：
    该行自检通过，但 seq=3 的 prev_chain_hash 仍指向旧 chain_hash → 在 seq=3 断裂。
    这正是哈希链的价值：篡改一行必须重写整条后继链，否则必被发现。"""
    _build_chain(client, requester, worker)
    with engine.begin() as conn:
        prev = conn.execute(
            sa.text("SELECT prev_chain_hash FROM anchor_entries WHERE seq = 2")
        ).scalar()
        forged_payload = '{"status": "released", "amount_cents": 999999}'
        forged_ph = _sha(forged_payload)
        forged_chain = _sha(prev + forged_ph)  # 自洽：满足本行三重校验
        conn.execute(
            sa.text(
                "UPDATE anchor_entries SET payload=:p, payload_hash=:h, chain_hash=:c WHERE seq = 2"
            ),
            {"p": forged_payload, "h": forged_ph, "c": forged_chain},
        )
    v = client.get("/api/v1/anchors/verify").json()
    # seq=2 自洽通过，断裂点落在 seq=3（其 prev 指向被改前的旧 chain_hash）
    assert v["valid"] is False and v["broken_at_seq"] == 3


def test_deleting_middle_entry_breaks_chain(client, requester, worker):
    """删除中间存证（seq=2）→ seq=3 的 prev 指向已消失的 chain_hash，链断裂。"""
    _build_chain(client, requester, worker)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM anchor_entries WHERE seq = 2"))
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is False and v["broken_at_seq"] == 3 and v["total"] == 2


def test_genesis_linkage_enforced(client, requester, worker):
    """篡改首条的 prev_chain_hash（脱离创世锚点）→ 首条即断裂。"""
    _build_chain(client, requester, worker)
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE anchor_entries SET prev_chain_hash = :p WHERE seq = 1"),
                     {"p": "f" * 64})
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is False and v["broken_at_seq"] == 1


def test_untampered_chain_head_is_stable_and_valid(client, requester, worker):
    """未篡改链：verify 返回 valid 且 head 等于末条 chain_hash（可对外公示锚定）。"""
    _build_chain(client, requester, worker)
    with engine.begin() as conn:
        head_db = conn.execute(
            sa.text("SELECT chain_hash FROM anchor_entries ORDER BY seq DESC LIMIT 1")
        ).scalar()
    v = client.get("/api/v1/anchors/verify").json()
    assert v["valid"] is True and v["head"] == head_db
