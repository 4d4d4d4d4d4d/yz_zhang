"""ESCA-052 按类别 / 优先级的工单 SLA（172 号 spec，V199）。

以前所有工单同一个时限：钱没到账和「怎么改头像」都是 4 小时首次响应、24 小时处理。
现在提单时选类别：资金、账号类加急（1 小时首次响应、8 小时处理、16 小时升级主管）；不选按一般（时限不变）。
客服可以把选错类别的改成加急或改回一般（写理由、进审计）。
"""


from app.core.config import settings
from app.core.db import SessionLocal

from app.modules.admin.models import AdminAudit
from app.modules.support.models import Ticket
from tests.conftest import JOB_HEADERS, auth, register
from tests.test_ticket_assign_reply import _admin, _age, _titles

API = "/api/v1"
JOB = f"{API}/admin/jobs/escalate-tickets"


def _create(client, u, category=None, subject="提现三天没到账"):
    body = {"subject": subject, "body": "急"}
    if category:
        body["category"] = category
    r = client.post(f"{API}/support/tickets", json=body, headers=auth(u))
    assert r.status_code == 201, r.text
    return r.json()


def test_funds_and_account_tickets_get_the_urgent_clock(client):
    u = register(client, "13800350001", "提单人")
    t = _create(client, u, "funds")
    assert t["priority"] == "urgent"
    row = next(x for x in client.get(f"{API}/support/tickets", headers=auth(u)).json() if x["id"] == t["id"])
    from tests.test_client_shape_alignment import _assert_shape

    _assert_shape(row, "MyTicket")
    assert (row["category"], row["priority"], row["priority_label"]) == ("funds", "urgent", "加急")
    assert row["sla_hours"] == settings.SUPPORT_URGENT_SLA_HOURS and row["first_response_hours"] == settings.SUPPORT_URGENT_FIRST_RESPONSE_HOURS
    plain = _create(client, u)
    prow = next(x for x in client.get(f"{API}/support/tickets", headers=auth(u)).json() if x["id"] == plain["id"])
    assert prow["priority"] == "normal" and prow["sla_hours"] == settings.SUPPORT_SLA_HOURS, "不选类别时限不变"
    bad = client.post(f"{API}/support/tickets", json={"subject": "x" * 3, "category": "vip"}, headers=auth(u))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "ticket_bad_category"


def test_escalation_job_uses_the_shorter_clock_for_urgent_tickets(client):
    agent = _admin(client, "13800350011", ["support"])
    boss = _admin(client, "13800350012", ["super"])
    u = register(client, "13800350013", "提单人")
    urgent = _create(client, u, "account", "登录不了，验证码收不到")
    normal = _create(client, u, None, "怎么改头像")
    _age(urgent["id"], settings.SUPPORT_URGENT_SLA_HOURS + 1)
    _age(normal["id"], settings.SUPPORT_URGENT_SLA_HOURS + 1)
    r = client.post(JOB, headers=JOB_HEADERS).json()
    assert urgent["id"] in r["level1"] and normal["id"] not in r["level1"], "同样等了 9 小时，只有加急的超时"
    assert urgent["id"] in r["first_response_alerts"] and normal["id"] in r["first_response_alerts"]
    _age(urgent["id"], settings.SUPPORT_URGENT_ESCALATE_L2_HOURS + 1)
    r2 = client.post(JOB, headers=JOB_HEADERS).json()
    assert urgent["id"] in r2["level2"]
    assert any("工单升级" in t for t in _titles(client, boss))
    assert any("工单超时" in t for t in _titles(client, agent)), "加急超时叫醒客服"


def test_support_can_change_priority_with_a_reason_and_the_clock_follows(client):
    agent = _admin(client, "13800350021", ["support"])
    ops = _admin(client, "13800350022", ["ops"])
    u = register(client, "13800350023", "提单人")
    t = _create(client, u, None, "钱一直没到")
    r = client.post(f"{API}/admin/tickets/{t['id']}/priority", json={"priority": "urgent", "reason": "其实是提现没到账"}, headers=auth(agent))
    assert r.status_code == 200, r.text
    from tests.test_client_shape_alignment import _assert_shape

    out = r.json()
    _assert_shape(out, "TicketPriorityUpdated")
    assert out["priority"] == "urgent" and out["sla_hours"] == settings.SUPPORT_URGENT_SLA_HOURS
    with SessionLocal() as db:
        a = db.query(AdminAudit).filter(AdminAudit.action == "ticket_priority").one()
        assert "其实是提现没到账" in a.detail and "normal -> urgent" in a.detail
    assert client.post(f"{API}/admin/tickets/{t['id']}/priority", json={"priority": "urgent", "reason": "测试"}, headers=auth(ops)).status_code == 403
    bad = client.post(f"{API}/admin/tickets/{t['id']}/priority", json={"priority": "highest", "reason": "测试"}, headers=auth(agent))
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "ticket_bad_priority"
    with SessionLocal() as db:
        db.get(Ticket, t["id"]).status = "resolved"
        db.commit()
    closed = client.post(f"{API}/admin/tickets/{t['id']}/priority", json={"priority": "normal", "reason": "测试"}, headers=auth(agent))
    assert closed.status_code == 409 and closed.json()["detail"]["code"] == "ticket_not_open"


def test_urgent_comes_first_in_the_urgent_sort(client):
    agent = _admin(client, "13800350031", ["support"])
    u = register(client, "13800350032", "提单人")
    older = _create(client, u, None, "一般问题")
    _age(older["id"], 5)
    newer = _create(client, u, "funds", "钱没到")
    rows = client.get(f"{API}/admin/tickets?status=open&sort=urgent", headers=auth(agent)).json()
    items = rows["items"] if isinstance(rows, dict) else rows
    ids = [x["id"] for x in items]
    assert ids.index(newer["id"]) < ids.index(older["id"]), "加急的排在前面，哪怕更晚提交"
