"""ESCA-059 「谢谢」类回复不再误重开已结工单（218 号 spec，V246）。

已结的单，用户回一句「谢谢」「收到」「已解决」，以前照样重新打开、叫醒客服。现在整句只是这类话的：照常记进往来，
但工单保持已结、不通知客服；带了别的内容（「谢谢，但还是不行」）照旧重开。
"""
import pytest

from app.modules.support.router import thanks_only
from tests.test_ticket_assign_reply import _admin, _ticket, _titles
from tests.test_ticket_user_reply import API, _reply
from tests.conftest import auth


@pytest.mark.parametrize("text,expect", [
    ("谢谢！", True), ("好的，谢谢🙏", True), ("收到 thanks", True), ("已解决，感谢", True), ("OK", True),
    ("谢谢，但还是不行", False), ("还没到账", False), ("谢谢" * 15, False), ("", False)])
def test_thanks_only_rule(text, expect):
    assert thanks_only(text) is expect, text


def test_thanks_keeps_a_resolved_ticket_closed_and_does_not_wake_staff(client):
    agent = _admin(client, "13800320101", ["support"])
    u, tid = _ticket(client, "13800320102")
    client.post(f"{API}/admin/tickets/{tid}/claim", headers=auth(agent))
    client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "已处理，请查收"}, headers=auth(agent))
    before = len(_titles(client, agent))
    r = _reply(client, u, tid, "好的，谢谢！")
    assert r.status_code == 200, r.text
    row = r.json()
    assert (row["reopened"], row["kept_closed"], row["status"]) == (False, True, "resolved")
    assert row["replies"][-1]["body"] == "好的，谢谢！", "照常记进往来"
    assert len(_titles(client, agent)) == before, "只说谢谢不打扰客服"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "MyTicketReplied")
    again = _reply(client, u, tid, "谢谢，但还是没到账")
    assert (again.json()["reopened"], again.json()["kept_closed"], again.json()["status"]) == (True, False, "open")


def test_thanks_on_an_open_ticket_is_just_a_reply(client):
    u, tid = _ticket(client, "13800320103")
    r = _reply(client, u, tid, "谢谢")
    assert (r.json()["reopened"], r.json()["kept_closed"], r.json()["status"]) == (False, False, "open")
