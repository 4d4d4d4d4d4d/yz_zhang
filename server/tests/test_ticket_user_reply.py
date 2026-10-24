"""ESCA-056 提单人在工单里追加回复（166 号 spec，V193）。

此前往来只有客服能回：用户想补一张截图说明、或者说「还是没到账」，只能再开一张工单——
两张单两个客服，前一张的上下文就丢了。已结的 7 天内追加会重新打开（与常见客服系统一致），
更早的请新开一张；转了纠纷的到纠纷里补（仲裁员只看纠纷里的）。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.support.models import Ticket, TicketReply
from tests.conftest import auth, register
from tests.test_ticket_assign_reply import _admin, _ticket, _titles

API = "/api/v1"


def _reply(client, u, tid, body):
    return client.post(f"{API}/support/tickets/{tid}/replies", json={"body": body}, headers=auth(u))


def test_user_reply_lands_in_the_thread_and_wakes_the_assignee(client):
    agent = _admin(client, "13800320001", ["support"])
    u, tid = _ticket(client, "13800320002")
    client.post(f"{API}/admin/tickets/{tid}/claim", headers=auth(agent))
    r = _reply(client, u, tid, "补充：银行卡尾号 1234，提现时间是昨天下午")
    assert r.status_code == 200, r.text
    row = r.json()
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "MyTicketReplied")
    assert row["reopened"] is False and row["status"] == "open"
    assert row["replies"][-1]["is_staff"] is False and "尾号 1234" in row["replies"][-1]["body"]
    assert any(f"工单 #{tid} 提单人补充了内容" in t for t in _titles(client, agent)), "接手的客服要知道"
    # 客服在后台看得到往来里提单人这一句
    admin_rows = client.get(f"{API}/admin/tickets?status=open", headers=auth(agent)).json()
    items = admin_rows["items"] if isinstance(admin_rows, dict) else admin_rows
    mine = next(x for x in items if x["id"] == tid)
    assert "尾号 1234" in mine["last_user_reply"] and mine["awaiting_staff"] is True and mine["replies_count"] == 0
    _assert_shape(mine, "AdminTicketRow")
    assert client.post(f"{API}/admin/tickets/{tid}/reply", json={"reply": "收到，正在查"}, headers=auth(agent)).status_code == 200
    again = client.get(f"{API}/admin/tickets?status=open", headers=auth(agent)).json()
    mine = next(x for x in (again["items"] if isinstance(again, dict) else again) if x["id"] == tid)
    assert mine["awaiting_staff"] is False and mine["replies_count"] == 1, "客服回过之后不再算在等，提单人那句不算客服回复次数"


def test_reply_to_a_resolved_ticket_within_7_days_reopens_it_older_ones_need_a_new_ticket(client):
    agent = _admin(client, "13800320011", ["support"])
    u, tid = _ticket(client, "13800320012")
    assert client.post(f"{API}/admin/tickets/{tid}/resolve", json={"reply": "已处理，请查收"}, headers=auth(agent)).status_code == 200
    r = _reply(client, u, tid, "还是没到账")
    assert r.status_code == 200 and r.json()["reopened"] is True and r.json()["status"] == "open"
    with SessionLocal() as db:
        t = db.get(Ticket, tid)
        assert t.resolved_at is None
        t.status, t.resolved_at = "resolved", utcnow() - timedelta(days=8)
        db.commit()
    old = _reply(client, u, tid, "又没到账")
    assert old.status_code == 409 and old.json()["detail"]["code"] == "ticket_closed_too_long"
    assert f"#{tid}" in old.json()["detail"]["message"], "要告诉他新开一张时写上原单号"


def test_only_my_ticket_not_after_dispute_not_empty_and_capped(client, monkeypatch):
    u, tid = _ticket(client, "13800320021")
    other = register(client, "13800320022", "别人")
    assert _reply(client, other, tid, "我也来说一句").status_code == 404
    assert _reply(client, u, tid, "   ").status_code == 409
    from app.modules.support import router as support_router

    monkeypatch.setattr(support_router, "MAX_USER_REPLIES", 2)
    assert _reply(client, u, tid, "一").status_code == 200
    assert _reply(client, u, tid, "二").status_code == 200
    capped = _reply(client, u, tid, "三")
    assert capped.status_code == 409 and capped.json()["detail"]["code"] == "ticket_reply_limit"
    with SessionLocal() as db:
        db.get(Ticket, tid).escalated_to_dispute_id = 77
        db.commit()
    d = _reply(client, u, tid, "补充材料")
    assert d.status_code == 409 and d.json()["detail"]["code"] == "ticket_in_dispute" and "#77" in d.json()["detail"]["message"]
    with SessionLocal() as db:
        assert db.query(TicketReply).filter(TicketReply.ticket_id == tid, TicketReply.is_staff.is_(False)).count() == 2
