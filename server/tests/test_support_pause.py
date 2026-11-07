"""ESCA-065 客服暂停接单（240 号 spec，V267）。

V264 让新工单自动分给打开了「自动分给我」的客服，但下班、请假时只能把勾去掉，回来还得记得勾回去；
忘了去掉，新工单就分给了不在的人，用户干等。现在可以「暂停接单 N 小时」：这段时间不自动分给他、
超时提醒先叫别人；到点自动恢复，也能提前恢复。
"""
from datetime import timedelta

from app.core.db import SessionLocal
from app.modules.account.models import utcnow
from app.modules.admin.models import AdminAudit
from app.modules.support import escalation
from app.modules.support.models import SupportAgentScope, Ticket
from tests.conftest import auth
from tests.test_support_scopes import API, _ticket
from tests.test_ticket_assign_reply import _admin

PAUSE = f"{API}/admin/support/my-pause"


def _opt_in(client, a, cats=("funds",)):
    client.put(f"{API}/admin/support/my-categories", json={"categories": list(cats), "auto_assign": True}, headers=auth(a))


def test_paused_agent_is_skipped_by_auto_assign_until_resumed(client):
    a = _admin(client, "13800340001", ["support"])
    b = _admin(client, "13800340002", ["support"])
    _opt_in(client, a)
    _opt_in(client, b)
    r = client.post(PAUSE, json={"hours": 8}, headers=auth(a))
    assert r.status_code == 200 and r.json()["paused_until"]
    from datetime import datetime

    until = datetime.fromisoformat(r.json()["paused_until"].replace("Z", "+00:00")).replace(tzinfo=None)
    assert timedelta(hours=7, minutes=59) < until - utcnow() <= timedelta(hours=8), "暂停到「现在 + 选的小时数」"
    me = client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    assert me["paused_until"] == r.json()["paused_until"] and me["auto_assign"] is True, "暂停不动「自动分给我」的勾"
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(me, "SupportScope")
    assert "paused_until" not in client.get(f"{API}/admin/support/my-categories", headers=auth(b)).json(), "没暂停时响应与以前一样"
    t1 = _ticket(client, "13800340003", "funds")
    t2 = _ticket(client, "13800340004", "funds")
    with SessionLocal() as db:
        assert db.get(Ticket, t1).assignee_id == b["id"] and db.get(Ticket, t2).assignee_id == b["id"], "a 暂停中，都分给 b（哪怕 b 手上更多）"
    assert client.delete(PAUSE, headers=auth(a)).json() == {"paused_until": None}
    assert "paused_until" not in client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    t3 = _ticket(client, "13800340005", "funds")
    with SessionLocal() as db:
        assert db.get(Ticket, t3).assignee_id == a["id"], "恢复后照常按负载分：a 手上 0 个"
        acts = [x.action for x in db.query(AdminAudit).filter(AdminAudit.admin_id == a["id"])]
        assert "support_pause" in acts and "support_resume" in acts


def test_pause_expires_by_itself_and_everyone_paused_still_gets_reminded(client):
    a = _admin(client, "13800340011", ["support"])
    b = _admin(client, "13800340012", ["support"])
    _opt_in(client, a)
    client.post(PAUSE, json={"hours": 1}, headers=auth(a))
    with SessionLocal() as db:                       # 时间过了：自动恢复，不用谁去点
        row = db.query(SupportAgentScope).filter(SupportAgentScope.user_id == a["id"]).one()
        row.paused_until = utcnow() - timedelta(minutes=1)
        db.commit()
    assert "paused_until" not in client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    t1 = _ticket(client, "13800340013", "funds")
    with SessionLocal() as db:
        t = db.get(Ticket, t1)
        assert t.assignee_id == a["id"]
        t.assignee_id = None                          # 不提交：只看「没人接手时提醒叫谁」
        assert sorted(escalation.level1_recipients(db, t)) == sorted([a["id"], b["id"]]), "过期的暂停不算暂停"
    # 超时提醒：暂停的人先不叫
    client.post(PAUSE, json={"hours": 2}, headers=auth(a))
    t2 = _ticket(client, "13800340014", "funds")
    with SessionLocal() as db:
        t = db.get(Ticket, t2)
        assert t.assignee_id is None, "暂停中又只有他打开了自动分配：不分，进公共队列"
        assert escalation.level1_recipients(db, t) == [b["id"]]
    client.post(PAUSE, json={"hours": 2}, headers=auth(b))
    with SessionLocal() as db:
        assert sorted(escalation.level1_recipients(db, db.get(Ticket, t2))) == sorted([a["id"], b["id"]]), "都暂停了照旧叫全部：不能没人管"


def test_pause_validation_roles_and_no_scope_row(client):
    a = _admin(client, "13800340021", ["support"])          # 没声明过负责类别
    assert client.post(PAUSE, json={"hours": 0}, headers=auth(a)).status_code == 422
    assert client.post(PAUSE, json={"hours": 24 * 30 + 1}, headers=auth(a)).status_code == 422
    assert client.post(PAUSE, json={"hours": 3, "x": 1}, headers=auth(a)).status_code == 422
    assert client.post(PAUSE, json={"hours": 3}, headers=auth(a)).status_code == 200
    me = client.get(f"{API}/admin/support/my-categories", headers=auth(a)).json()
    assert me["categories"] == ["funds", "account", "general"] and me["paused_until"], "补的一行照「什么都管」的意思"
    fin = _admin(client, "13800340022", ["finance"])
    assert client.post(PAUSE, json={"hours": 3}, headers=auth(fin)).status_code == 403
    assert client.delete(PAUSE, headers=auth(fin)).status_code == 403
    other = _admin(client, "13800340023", ["support"])
    assert client.delete(PAUSE, headers=auth(other)).json() == {"paused_until": None}, "没暂停也能点恢复（幂等）"
