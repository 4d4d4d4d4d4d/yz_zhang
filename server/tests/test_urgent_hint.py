"""ESCA-060 自选加急的滥用提示（229 号 spec，V256）。

V178 让用户自己选「资金 / 账号」类加急，客服可以改回一般并留痕（ESCA-052）。什么都选加急的人，
会把真正着急的人挤到后面。现在近 90 天自选加急 ≥3 张、过半被改回的，提单页和提交后都提示一句；不拦。
客服队列里每张单写明提单人近 90 天自选加急被改回的情况。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.support.models import Ticket
from tests.conftest import auth, register
from tests.test_ticket_assign_reply import _admin

API = "/api/v1"


def _urgent(client, u, n):
    return [client.post(f"{API}/support/tickets", json={"subject": f"钱没到账 {i}", "category": "funds"}, headers=auth(u)).json()
            for i in range(n)]


def _downgrade(client, agent, tid):
    r = client.post(f"{API}/admin/tickets/{tid}/priority", json={"priority": "normal", "reason": "其实是问怎么开发票"}, headers=auth(agent))
    assert r.status_code == 200, r.text


def test_hint_appears_only_with_enough_samples_and_majority_downgraded(client):
    u = register(client, "13800329001", "常选加急")
    agent = _admin(client, "13800329002", ["support"])
    first = _urgent(client, u, 2)
    assert all(x["priority_note"] == "" for x in first)
    _downgrade(client, agent, first[0]["id"])
    _downgrade(client, agent, first[1]["id"])
    h = client.get(f"{API}/support/tickets/urgent-hint", headers=auth(u)).json()
    assert (h["self_urgent"], h["downgraded"], h["message"]) == (2, 2, ""), "两张不下结论"
    third = _urgent(client, u, 1)[0]
    assert "3 张工单里，有 2 张被客服改回了一般" in third["priority_note"] and third["priority"] == "urgent", "提示但不拦"
    h = client.get(f"{API}/support/tickets/urgent-hint", headers=auth(u)).json()
    assert h["days"] == 90 and h["message"].startswith("你最近 90 天选了加急的 3 张工单里，有 2 张")
    # 选「一般」不提示
    r = client.post(f"{API}/support/tickets", json={"subject": "问个问题"}, headers=auth(u)).json()
    assert r["priority_note"] == ""
    # 改回的同一张改来改去只算一次；没过半不提示
    client.post(f"{API}/admin/tickets/{first[0]['id']}/priority", json={"priority": "urgent", "reason": "又确认是钱的事"}, headers=auth(agent))
    _downgrade(client, agent, first[0]["id"])
    _urgent(client, u, 2)
    h = client.get(f"{API}/support/tickets/urgent-hint", headers=auth(u)).json()
    assert (h["self_urgent"], h["downgraded"], h["message"]) == (5, 2, "")


def test_old_tickets_fall_out_and_queue_shows_requester_record(client):
    u = register(client, "13800329003", "很久以前")
    agent = _admin(client, "13800329004", ["support"])
    rows = _urgent(client, u, 3)
    for r in rows:
        _downgrade(client, agent, r["id"])
    # 客服把一张加急的又点成加急（没变化）：审计里有一条 urgent -> urgent，不算改回
    kept = _urgent(client, u, 1)[0]
    client.post(f"{API}/admin/tickets/{kept['id']}/priority", json={"priority": "urgent", "reason": "确认是钱的事"}, headers=auth(agent))
    rows.append(kept)
    q = {x["id"]: x for x in client.get(f"{API}/admin/tickets", headers=auth(agent)).json()}
    assert (q[rows[0]["id"]]["requester_urgent_90d"], q[rows[0]["id"]]["requester_downgraded_90d"]) == (4, 3)
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(q[rows[0]["id"]], "AdminTicketRow")
    with SessionLocal() as db:
        for r in rows:
            db.get(Ticket, r["id"]).created_at = utcnow() - timedelta(days=91)
        db.commit()
    h = client.get(f"{API}/support/tickets/urgent-hint", headers=auth(u)).json()
    assert (h["self_urgent"], h["message"]) == (0, ""), "90 天以前的不算"
