"""ESCA-058 后台工单详情与完整往来（221 号 spec，V249）。

后台队列只露提单人最新一句与回复次数；完整往来以前哪里都看不到——接手的客服不知道前一位说过什么。
"""
from tests.conftest import auth
from tests.test_ticket_assign_reply import _admin, _ticket
from tests.test_ticket_user_reply import API, _reply


def test_detail_shows_the_whole_thread_with_who_said_what(client):
    agent = _admin(client, "13800321001", ["support"])
    u, tid = _ticket(client, "13800321002")
    client.post(f"{API}/admin/tickets/{tid}/claim", headers=auth(agent))
    client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "在查了，请补一张截图"}, headers=auth(agent))
    _reply(client, u, tid, "截图在这：尾号 1234")
    r = client.get(f"{API}/admin/tickets/{tid}", headers=auth(agent))
    assert r.status_code == 200, r.text
    d = r.json()
    assert [(x["author"], x["is_staff"], x["body"]) for x in d["thread"]] == [
        (d["assignee_nickname"], True, "在查了，请补一张截图"), ("提单人", False, "截图在这：尾号 1234")]
    assert d["assignee_id"] == agent["id"] and d["status"] == "open" and d["body"]
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(d, "AdminTicketDetail")
    _assert_shape(d["thread"][0], "AdminTicketThreadItem")
    # 提单人那一侧仍然只看到「客服」，看不到是哪位
    mine = client.get(f"{API}/support/tickets", headers=auth(u)).json()[0]
    assert "author" not in mine["replies"][0]


def test_only_support_staff_and_missing_ticket(client):
    u, tid = _ticket(client, "13800321003")
    assert client.get(f"{API}/admin/tickets/{tid}", headers=auth(u)).status_code == 403
    finance = _admin(client, "13800321004", ["finance"])
    assert client.get(f"{API}/admin/tickets/{tid}", headers=auth(finance)).status_code == 403
    agent = _admin(client, "13800321005", ["support"])
    assert client.get(f"{API}/admin/tickets/999999", headers=auth(agent)).status_code == 404
