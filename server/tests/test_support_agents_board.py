"""ESCA-066 主管看全体客服的状态并替人恢复接单（248 号 spec，V275）。

240 号让客服可以暂停接单，但主管看不到谁在、谁不在、谁手上压了几张；有人请假回来忘了恢复，
新工单就一直绕开他。现在主管能看全体客服的状态，并替人提前恢复。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.admin.models import AdminAudit
from app.modules.support.models import SupportAgentScope, Ticket
from tests.conftest import auth
from tests.test_support_pause import PAUSE, _opt_in
from tests.test_support_scopes import API, _ticket
from tests.test_ticket_assign_reply import _admin, _titles

BOARD = f"{API}/admin/support/agents"


def test_supervisor_sees_every_agent_and_resumes_one(client):
    boss = _admin(client, "13800348001", ["super"])
    a = _admin(client, "13800348002", ["support"])
    b = _admin(client, "13800348003", ["support"])
    _admin(client, "13800348004", ["finance"])                   # 不是客服，不在表里
    _opt_in(client, a, ("funds", "account"))
    client.post(PAUSE, json={"hours": 8}, headers=auth(a))
    t = _ticket(client, "13800348005", "general")
    client.post(f"{API}/admin/tickets/{t}/claim", headers=auth(b))
    done = _ticket(client, "13800348006", "general")
    with SessionLocal() as db:
        d = db.get(Ticket, done)
        d.assignee_id, d.status = b["id"], "resolved"                 # 已结的不算手上的
        db.commit()
    c = _admin(client, "13800348007", ["support"])
    client.post(PAUSE, json={"hours": 1}, headers=auth(c))
    with SessionLocal() as db:
        db.query(SupportAgentScope).filter(SupportAgentScope.user_id == c["id"]).one().paused_until = utcnow() - timedelta(minutes=5)
        db.commit()
    rows = {r["user_id"]: r for r in client.get(BOARD, headers=auth(boss)).json()}
    assert set(rows) == {boss["id"], a["id"], b["id"], c["id"]}, "能处理工单的人（含超级管理员），别的角色不在"
    assert rows[c["id"]]["paused_until"] is None, "暂停已经过期：算在岗"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(rows[a["id"]], "SupportAgentStatus")
    assert (rows[a["id"]]["categories"], rows[a["id"]]["declared"], rows[a["id"]]["auto_assign"]) == (["funds", "account"], True, True)
    assert rows[a["id"]]["paused_until"] and rows[b["id"]]["paused_until"] is None
    assert (rows[b["id"]]["open_tickets"], rows[a["id"]]["open_tickets"]) == (1, 0)
    assert rows[b["id"]]["declared"] is False and rows[b["id"]]["categories"] == ["funds", "account", "general"]
    r = client.delete(f"{BOARD}/{a['id']}/pause", headers=auth(boss))
    assert r.status_code == 200 and r.json() == {"user_id": a["id"], "paused_until": None}
    assert "paused_until" not in client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    assert "主管已恢复你的接单" in _titles(client, a)
    again = client.delete(f"{BOARD}/{a['id']}/pause", headers=auth(boss))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "support_agent_not_paused"
    with SessionLocal() as db:
        assert db.query(AdminAudit).filter(AdminAudit.action == "support_resume_by_supervisor").count() == 1
        assert db.get(Ticket, t).assignee_id == b["id"]


def test_only_supervisors(client):
    a = _admin(client, "13800348011", ["support"])
    client.post(PAUSE, json={"hours": 8}, headers=auth(a))
    b = _admin(client, "13800348012", ["support"])
    assert client.get(BOARD, headers=auth(b)).status_code == 403, "普通客服看不到全体"
    assert client.delete(f"{BOARD}/{a['id']}/pause", headers=auth(b)).status_code == 403, "也不能替别人恢复"
