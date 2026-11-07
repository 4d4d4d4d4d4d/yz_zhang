"""ESCA-053 首次响应 / ESCA-054 主管指派（157 号 spec）。

V178 之后客服只能「认领」和「回复并结单」：一张要查两天的单，提单人两天里一句话都收不到；
主管看到积压，也只能挨个去叫人认领。
"""
from datetime import timedelta

from app.core.config import settings
from app.core.db import SessionLocal
from app.modules.account.models import User, utcnow
from app.modules.admin.models import AdminAudit
from app.modules.support.models import Ticket, TicketReply
from tests.conftest import JOB_HEADERS, auth, make_admin, register

API = "/api/v1"
JOB = f"{API}/admin/jobs/escalate-tickets"


def _admin(client, phone, roles):
    a = make_admin(client, phone, f"管理员{phone[-2:]}")
    with SessionLocal() as db:
        db.get(User, a["id"]).admin_roles = roles
        db.commit()
    return a


def _ticket(client, phone, subject="提现三天没到账"):
    u = register(client, phone, "提问的人")
    tid = client.post(f"{API}/support/tickets", json={"subject": subject, "body": "急"}, headers=auth(u)).json()["id"]
    return u, tid


def _age(tid, hours):
    with SessionLocal() as db:
        db.get(Ticket, tid).created_at = utcnow() - timedelta(hours=hours)
        db.commit()


def _titles(client, user):
    rows = client.get(f"{API}/notifications?limit=100", headers=auth(user)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    return [n["title"] for n in items]


def test_reply_without_closing_counts_as_first_response(client):
    s1 = _admin(client, "13800310001", ["support"])
    u, tid = _ticket(client, "13800310002")
    r = client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "在查了，麻烦补一张银行短信截图"}, headers=auth(s1))
    assert r.status_code == 200, r.text
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(r.json(), "TicketReplied")
    assert r.json()["status"] == "open" and r.json()["first_response_at"] and r.json()["replies"] == 1
    assert "客服回复了你的工单" in _titles(client, u)
    first_at = r.json()["first_response_at"]
    r2 = client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "已找到原因，银行退回了"}, headers=auth(s1)).json()
    assert r2["first_response_at"] == first_at and r2["replies"] == 2, "首次响应时间只记第一次"
    client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "已重新打款"}, headers=auth(s1))
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert [x["body"] for x in mine["replies"]] == ["在查了，麻烦补一张银行短信截图", "已找到原因，银行退回了", "已重新打款"]
    assert mine["reply"] == "已重新打款" and mine["first_responded"] is True, "原有的 reply 字段仍是最近一次回复"
    assert all("author_id" not in x for x in mine["replies"]), "提单人看不到是哪位管理员"
    _assert_shape(mine, "MyTicket")


def test_resolving_directly_also_records_first_response(client):
    s1 = _admin(client, "13800310011", ["support"])
    _u, tid = _ticket(client, "13800310012")
    client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "已处理"}, headers=auth(s1))
    with SessionLocal() as db:
        assert db.get(Ticket, tid).first_response_at is not None
        assert db.query(TicketReply).filter(TicketReply.ticket_id == tid).count() == 1


def test_first_response_overdue_alerts_once_and_not_after_a_reply(client, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_FIRST_RESPONSE_HOURS", 4)
    s1 = _admin(client, "13800310021", ["support"])
    _u, tid = _ticket(client, "13800310022")
    _u2, replied = _ticket(client, "13800310023")
    client.post(f"{API}/admin/tickets/{replied}/reply", json={"reply": "在处理"}, headers=auth(s1))
    _age(tid, 3)
    assert client.post(JOB, headers=JOB_HEADERS).json()["first_response_alerts"] == []
    _age(tid, 5)
    _age(replied, 5)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert r["first_response_alerts"] == [tid] and r["level1"] == [], "首次响应与解决时限各算各的"
    assert _titles(client, s1).count("工单首次响应超时") == 1
    assert client.post(JOB, headers=JOB_HEADERS).json()["first_response_alerts"] == []
    rows = {x["id"]: x for x in client.get(f"{API}/admin/tickets", headers=auth(s1)).json()}
    assert rows[tid]["first_response_overdue"] is True and rows[replied]["first_response_overdue"] is False
    assert rows[replied]["replies_count"] == 1 and rows[tid]["first_response_hours"] == 4


def test_supervisor_assigns_to_a_support_agent(client):
    boss = _admin(client, "13800310031", ["super"])
    s1 = _admin(client, "13800310032", ["support"])
    fin = _admin(client, "13800310033", ["finance"])
    _u, tid = _ticket(client, "13800310034")
    url = f"{API}/admin/tickets/{tid}/assign"
    assert client.post(url, json={"assignee_id": s1["id"]}, headers=auth(s1)).status_code == 403, "只有主管能指派"
    bad = client.post(url, json={"assignee_id": fin["id"]}, headers=auth(boss))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "assignee_not_support"
    r = client.post(url, json={"assignee_id": s1["id"]}, headers=auth(boss))
    assert r.status_code == 200 and r.json()["assignee_id"] == s1["id"]
    assert "你被指派了一张工单" in _titles(client, s1)
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "ticket_assign").one()
        assert a.admin_id == boss["id"] and f"#{s1['id']}" in a.detail
    # 指派之后超时只叫醒被指派的人
    rows = client.get(f"{API}/admin/tickets", params={"mine": True}, headers=auth(s1)).json()
    assert [x["id"] for x in rows] == [tid]
    client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "好了"}, headers=auth(s1))
    assert client.post(url, json={"assignee_id": s1["id"]}, headers=auth(boss)).status_code == 404
